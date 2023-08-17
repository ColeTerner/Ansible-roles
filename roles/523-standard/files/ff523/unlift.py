#!/usr/bin/python3
import base64
import subprocess
import configparser
import datetime
import threading
import time
import getopt
import json
import mimetypes
import os
import re
import sys
import traceback
import zipfile
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Event, Thread, Lock
from urllib.parse import urlparse

import motor.motor_tornado
import sqlite3
import tornado.concurrent
import tornado.escape
import tornado.httpclient
import tornado.httputil
import tornado.ioloop
import tornado.web
import tornado.websocket
from PIL import Image
from tornado.httputil import url_concat

Rectangle = namedtuple('Rectangle', 'xmin ymin xmax ymax')


def transliterate(name):
    trans_dict = {'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
              'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'i', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
              'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h',
              'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e',
              'ю': 'u', 'я': 'ya', 'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'YO',
              'Ж': 'ZH', 'З': 'Z', 'И': 'I', 'Й': 'I', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N',
              'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F', 'Х': 'H',
              'Ц': 'C', 'Ч': 'CH', 'Ш': 'SH', 'Щ': 'SCH', 'Ъ': '', 'Ы': 'y', 'Ь': '', 'Э': 'E',
              'Ю': 'U', 'Я': 'YA', ',': '', '?': '', ' ': '_', '~': '', '!': '', '@': '', '#': '',
              '$': '', '%': '', '^': '', '&': '', '*': '', '(': '', ')': '', '-': '', '=': '', '+': '',
              ':': '', ';': '', '<': '', '>': '', '\'': '', '"': '', '\\': '', '/': '', '№': '',
              '[': '', ']': '', '{': '', '}': '', 'ґ': '', 'ї': '', 'є': '', 'Ґ': 'g', 'Ї': 'i',
              'Є': 'e', '—': ''}

    for key in trans_dict:
        name = name.replace(key, trans_dict[key])
    return name


def print_escaped(item):
    try:
        trans_item = transliterate(str(item))
        print(trans_item)
    except:
        pass


class VisitTimeList:
    def __init__(self):
        self.__items__ = {}
        self.__thread_lock__ = Lock()

    def update_time(self, item_id):
        with self.__thread_lock__:
            self.__items__[item_id] = datetime.datetime.utcnow()

    def get_time(self, item_id):
        with self.__thread_lock__:
            return self.__items__.get(item_id)


class FaceCounter:
    def __init__(self):
        self.__face_counter__ = 0
        self.__last_sent_count__ = 0

    def get_count(self):
        return self.__face_counter__

    def get_last_sent_count(self):
        return self.__last_sent_count__

    def increase(self):
        self.__face_counter__ += 1

    def set_last_sent_count(self, count):
        self.__last_sent_count__ = count if count > self.__last_sent_count__ else self.__last_sent_count__

    def reset_counter(self):
        self.__face_counter__ = 0


class CameraStatsCounter:
    def __init__(self):
        self.__items__ = {}
        self.__thread_lock__ = Lock()

    def increase(self, camera):
        with self.__thread_lock__:
            if camera not in self.__items__.keys():
                self.__items__[camera] = FaceCounter()
            self.__items__[camera].increase()

    def get_count(self):
        with self.__thread_lock__:
            return list(map(lambda x: {'cameraGuid': x, 'count': self.__items__[x].get_count(),
                                       'last_sent_count': self.__items__[x].get_last_sent_count()},
                            self.__items__.keys()))

    def set_last_sent_count(self, camera, count):
        with self.__thread_lock__:
            if camera in self.__items__.keys():
                self.__items__[camera].set_last_sent_count(count)
            else:
                self.__items__[camera] = FaceCounter()


boundary_re = re.compile(r'boundary=(\S*);?')


# noinspection SqlNoDataSourceInspection,SqlResolve
def create_db(client):
    client.execute("""
CREATE TABLE IF NOT EXISTS proxy_file (
id INTEGER PRIMARY KEY AUTOINCREMENT,
path TEXT NULL,
score TEXT NULL,
dir_score TEXT NULL,
width TEXT NULL,
height TEXT NULL,
camera_id TEXT NULL,
x TEXT NULL,
y TEXT NULL,
datetime INTEGER NULL,
face_id TEXT NULL,
confidence TEXT NULL,
fails INTEGER NOT NULL DEFAULT 0)""")
    client.execute("""
CREATE TABLE IF NOT EXISTS proxy_log_record (
id INTEGER PRIMARY KEY AUTOINCREMENT,
file_id INTEGER NOT NULL, 
age TEXT NULL,
emotion TEXT NULL,
gender TEXT NULL,
similar_to INTEGER NULL,
FOREIGN KEY (file_id) REFERENCES proxy_file(id) ON DELETE CASCADE,
FOREIGN KEY (similar_to) REFERENCES proxy_file(id) ON DELETE SET NULL)""")
    client.commit()


# noinspection SqlNoDataSourceInspection,SqlResolve
def add_file(_sqlite_client, path, score, dir_score, width, height, x, y, camera_id, file_datetime, face_id,
             confidence, gender, age, emotion):
    int_time = int(file_datetime * 1000)
    _sqlite_client.execute("""
INSERT INTO proxy_file (path, score, dir_score, width, height, x, y, camera_id, datetime, face_id, confidence)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (path, score, dir_score, width, height, x, y, camera_id, int_time, face_id, confidence))
    cursor = _sqlite_client.cursor()
    cursor.execute("SELECT last_insert_rowid()")
    result = cursor.fetchall()
    file_id = result[0][0]
    _sqlite_client.execute("""
    INSERT INTO proxy_log_record (file_id, age, emotion, gender)
    VALUES (?, ?, ?, ?)""", (file_id, age, emotion, gender))

    _sqlite_client.commit()


def area(a, b):  # returns None if rectangles don't intersect
    dx = min(a.xmax, b.xmax) - max(a.xmin, b.xmin)
    dy = min(a.ymax, b.ymax) - max(a.ymin, b.ymin)
    if (dx >= 0) and (dy >= 0):
        return dx * dy


def zip_folder(folder_path):
    print('forming zip with path {}'.format(folder_path))
    result_folder = './tasks'
    if not os.path.exists(result_folder):
        os.makedirs(result_folder)
    output_filename = os.path.join(result_folder, datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S%f')) + '.zip'
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    dir_items = os.listdir(folder_path)
    jpg_files = list(filter(lambda x: os.path.isfile(os.path.join(folder_path, x)) and os.path.splitext(x)[1] == '.jpg',
                            dir_items))
    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file in jpg_files:
            zf.write(os.path.join(folder_path, file), file)

    return output_filename, len(jpg_files)


def crop_face(img, x1, x2, y1, y2, extended=False):
    if not extended:
        return img.crop((x1, y1, x2, y2))
    width = x2 - x1
    height = y2 - y1
    ext_x1 = x1 - int(round(0.5 * width))
    ext_x2 = x2 + int(round(0.5 * width))
    ext_y1 = y1 - int(round(0.5 * height))
    ext_y2 = y2 + int(round(0.5 * height))
    return img.crop((ext_x1, ext_y1, ext_x2, ext_y2))


def save_photo(cropped_img, score, direction_score, face_id,
               confidence, camera_guid, x1, y1, x2, y2, file_time, gender, age, emotion):
    current_date = datetime.datetime.utcnow()
    directory = form_directory_name(current_date)
    if not os.path.exists(directory):
        os.makedirs(directory)
    directory += current_date.strftime('%M%S%f')[:-3]
    info_tags = []
    if not gender:
        parsed_gender = 'e'
    elif gender.lower() == 'male':
        parsed_gender = 'm'
    elif gender.lower() == 'female':
        parsed_gender = 'f'
    else:
        parsed_gender = 'e'
    info_tags.append(parsed_gender)
    width = x2 - x1
    height = y2 - y1
    validated_age = age if age else 0
    validated_emotion = emotion if emotion else 'none'
    info_tags.append(str(round(validated_age)))
    info_tags.append(validated_emotion)
    info_tags.append(str(width))
    info_tags.append(str(height))
    info_tags.append(str(get_camera_number(camera_guid)))
    info_tags.append(str(score))
    info_tags.append(str(direction_score))
    if face_id:
        info_tags.append('alert' + str(face_id))
        info_tags.append("{:.2f}".format(confidence * 100))
    directory += '_' + '_'.join(info_tags)
    directory += '.jpg'
    cropped_img.save(directory, format='JPEG')
    with open('detect_log.txt', 'a') as detect_log:
        detect_log.write(';'.join([str(current_date), directory, *info_tags]) + '\n')
    global db_client
    add_file(db_client, directory, score, direction_score, width, height,
             x1, y1, camera_guid, file_time, face_id, confidence, parsed_gender, validated_age, validated_emotion)


def form_directory_name(current_time):
    directory = current_time.strftime('./%Y%m%d/%H/')
    directory += '{0}_{1}/'.format(current_time.minute // 10 * 10, (current_time.minute // 10 + 1) * 10)
    return directory


def on_ping_response(response):
    body = response.body
    global ping_error_counter
    try:
        parsed_body = json.loads(body.decode('utf8'))["data"]
        global monitoring
        global min_score
        global min_direction_score
        global min_face_size
        global max_face_size
        global save_detect
        global threshold
        global overseer_threshold
        global cameras_settings
        global is_recognition_enabled
        global must_play_on_incident
        global must_play_on_stuff
        global must_play_differ_sounds_by_gender
        global must_ignore_stuff_timer
        global incident_music_interval
        global staff_music_interval
        global should_play_sound
        global dns_ip

        monitoring = parsed_body.get("isUnderMonitoring")
        min_score = parsed_body.get("minScore")
        min_direction_score = parsed_body.get("minDirectionScore")
        min_face_size = parsed_body.get("minFaceSize")
        max_face_size = parsed_body.get("maxFaceSize")
        save_detect = parsed_body.get("saveDetectedFaces")
        received_threshold = parsed_body.get("threshold")
        received_overseer_threshold = parsed_body.get("overseerNotificationThreshold")
        cameras_settings = parsed_body.get("camerasSettings")
        is_recognition_enabled = parsed_body.get("isRecognitionEnabled")
        must_play_on_incident = parsed_body.get("mustPlayMusicOnIncident")
        must_play_on_stuff = parsed_body.get("mustPlayMusicOnStuff")
        must_play_differ_sounds_by_gender = parsed_body.get("mustPlayDifferSoundsByGender")
        must_ignore_stuff_timer = parsed_body.get("mustIgnoreStuffFreqTimer")
        incident_music_interval = parsed_body.get("incidentMusicInterval")
        staff_music_interval = parsed_body.get("stuffMusicInterval")
        should_play_sound = parsed_body.get("isSoundEnabled")
        dns_ip = parsed_body.get("dnsIp")

        if received_threshold:
            threshold = received_threshold
        if received_overseer_threshold:
            overseer_threshold = received_overseer_threshold
        print("is_recognition_enabled = " + str(is_recognition_enabled))
        print("monitoring = " + str(monitoring))
        print("save_faces = " + str(save_detect))
        print(parsed_body)
        ping_error_counter.reset_counter()
    except Exception as e:
        ping_error_counter.increase()
        print("PING Error: " + str(e) + "; " + str(response.error))


def on_get_tasks_response(response):
    body = response.body
    try:
        parsed_body = json.loads(body.decode('utf8'))["data"]
        global tasks
        global monitoring
        global is_recognition_enabled
        monitoring = parsed_body.get("isUnderMonitoring")
        is_recognition_enabled = parsed_body.get("isRecognitionEnabled")
        print("is_recognition_enabled = " + str(is_recognition_enabled))
        print("monitoring = " + str(monitoring))

        received_tasks = parsed_body.get("tasks")
        print("------- received tasks ---------")
        print(received_tasks)
        tasks = list(received_tasks)
        print("------- tasks ---------")
        print(tasks)
        print(parsed_body)
        print("/------------------ get tasks -------------")

    except Exception as e:
        print("GET TASK Error: " + str(e))


failed_logs = []
tasks = []
finished_tasks = []


def fetch_http_request(request: tornado.httpclient.HTTPRequest):
    http_client = tornado.httpclient.HTTPClient()
    result = None
    try:
        result = http_client.fetch(request)
    finally:
        http_client.close()
    return result


# noinspection SqlNoDataSourceInspection,SqlResolve
def upload_stats():
    global db_path
    client = sqlite3.connect(db_path)
    cursor = client.cursor()
    cursor.execute("""
    SELECT proxy_file.id, proxy_file.path, proxy_file.score, proxy_file.dir_score,
     proxy_file.width, proxy_file.height, proxy_file.camera_id,
      proxy_file.x, proxy_file.y, proxy_file.datetime, proxy_file.face_id,
       proxy_file.confidence, proxy_log_record.age, proxy_log_record.emotion, proxy_log_record.gender FROM proxy_file 
    LEFT JOIN proxy_log_record ON proxy_log_record.file_id = proxy_file.id
    WHERE proxy_log_record.id IS NOT NULL AND fails < 5 ORDER BY proxy_file.datetime LIMIT 5000""")
    results = cursor.fetchall()
    records = []
    last_datetime = 0
    print(results)
    for item in results:
        last_datetime = max(last_datetime, item[9])
        records.append({
            'folder': item[1],
            'score': item[2],
            'directScore': item[3],
            'width': item[4],
            'heigth': item[5],
            'cameraNumber': item[6],
            'x': item[7],
            'y': item[8],
            'datetime': item[9],
            'faceId': item[10],
            'confidence': item[11],
            'age': item[12],
            'emotion': item[13],
            'gender': item[14],
        })
    global disable_ssl
    result = fetch_http_request(tornado.httpclient.HTTPRequest(
            url=unlift_log_url,
            method='POST',
            headers={"Content-Type": 'application/json', "Host": "unlift.ru"},
            body=json.dumps({'items': records, 'token': unlift_token}),
            follow_redirects=False,
            request_timeout=120,
            validate_cert=not disable_ssl))
    if result.error is None:
        print(last_datetime)
        client.execute('DELETE FROM proxy_file WHERE datetime <= ? AND ' +
                       'id IN (SELECT file_id FROM proxy_log_record) OR fails > 4', (last_datetime,))
        client.commit()


def upload_photos(start_date, task_id):
    directory = form_directory_name(datetime.datetime.strptime(start_date, '%Y-%m-%dT%H:%M:%SZ'))
    zip_path, files_count = zip_folder(directory)
    print("zip path is {}".format(zip_path))
    with open(zip_path, mode='rb') as zip_file:
        zip_file_bytes = BytesIO(zip_file.read()).getvalue()
    if files_count > 0 and len(zip_file_bytes) <= 22:
        return
    data = [("token", unlift_token), ("taskId", task_id)]
    file = ('file', os.path.basename(zip_path), zip_file_bytes)
    content_type, body = encode_multipart_formdata(data, [file])
    global disable_ssl
    global upload_faces_url
    result = fetch_http_request(
        tornado.httpclient.HTTPRequest(
            url=upload_faces_url,
            method="POST",
            body=body,
            headers={"Content-Type": content_type, 'content-length': str(len(body)), "Host": "unlift.ru"},
            follow_redirects=False,
            request_timeout=120,
            validate_cert=not disable_ssl))
    if result.error is None:
        finished_tasks.append(task_id)


def play_test_sound(task):
    finished_tasks.append(task['id'])
    try:
        fetch_http_request(
            tornado.httpclient.HTTPRequest(
                url=finish_play_test_sound_url+'?token={}&taskId={}'.format(unlift_token, task['id']),
                method="POST",
                body='',
                headers={"Host": "unlift.ru"},
                follow_redirects=False,
                request_timeout=3,
                validate_cert=not disable_ssl))
    except:
        pass
    try:
        print('SOUND PLAYING TEST: RUNNING')
        sound_thread = threading.Thread(target=start_subproccess, args=(["ffplay", "-nodisp", "-autoexit", "warning.mp3"],))
        sound_thread.start()
        print('SOUND PLAYING TEST: EXECUTED')
    except Exception as e:
        print("Playing sound error: {}".format(str(e)))


def execute_task(task):
    parameters = task.get("parameters")
    if parameters is None:
        return
    if task['type'] == 1:
        upload_photos(parameters[0].get("dateTimeValue"), task['id'])
    elif task['type'] == 6:
        play_test_sound(task)


def run_tasks():
    try:
        global tasks
        tasks_to_run = list(filter(lambda x: x['id'] not in finished_tasks, tasks))[:5]
        for task in tasks_to_run:
            try:
                execute_task(task)
            except Exception as e:
                print("Task execution error: " + str(e))
        tasks = list(filter(lambda x: x['id'] not in finished_tasks, tasks))
    except Exception as e:
        print("Task execution error: " + str(e))


def get_request_timeout():
    global ping_error_counter
    if ping_error_counter.get_count() > 10:
        return 1800
    return 20


def send_ping_request():
    print("------------------ping-------------")
    global disable_ssl
    response = fetch_http_request(
        tornado.httpclient.HTTPRequest(
            url=url_concat(pingUrl, {'token': unlift_token, 'proxyVersion': proxy_version}),
            method='GET',
            headers={"Host": "unlift.ru"},
            follow_redirects=False,
            request_timeout=get_request_timeout(),
            validate_cert=not disable_ssl))
    on_ping_response(response)


def parse_cameras(camera_string):
    cameras = json.loads(camera_string.decode('utf8'))
    print(cameras)
    global cameras_guids
    cameras_guids = list(map(lambda x: x['cameraGuid'], cameras))
    print('cameras guids')
    print(cameras_guids)


def get_cameras(http_client_cam):
    global disable_ssl
    global get_cameras_url
    cam_response = http_client_cam.fetch(tornado.httpclient.HTTPRequest(
        url=get_cameras_url,
        method='GET',
        headers={"Host": "unlift.ru"},
        follow_redirects=False,
        validate_cert=not disable_ssl))
    camera_string = cam_response.body
    parse_cameras(camera_string)
    return camera_string


def get_filter_settings(camera):
    gpu_settings = camera.get('stream_settings_gpu')
    if gpu_settings is None:
        return None, None, None

    quality = gpu_settings.get('filter_min_quality')
    return quality, gpu_settings.get('filter_min_face_size'), gpu_settings.get(
        'filter_max_face_size')


def get_stats():
    uptime = subprocess.check_output('uptime', shell=True)
    uptime = uptime.decode('utf8').strip()
    load_avg = subprocess.check_output('cat /proc/loadavg', shell=True)
    avg1, avg2, avg3 = load_avg.decode('utf8').split(" ")[:3]
    free = subprocess.check_output('free', shell=True)
    memory, swap = free.decode('utf8').split('\n')[1:3]
    memory_values = memory.split()[1:]
    swap_values = swap.split()[1:]
    cpu_core_info = subprocess.check_output('dmidecode -t processor | grep -E \'(Core Count)\'', shell=True)
    cpu_cores_count = cpu_core_info.decode('utf8').split(':')[1].strip()

    jobs = fetch_http_request(
        tornado.httpclient.HTTPRequest(
            url="http://127.0.0.1:18810/jobs",
            method='GET',
            follow_redirects=False,
            request_timeout=2))
    parsed_jobs = json.loads(jobs.body.decode('utf8'))
    stats = list(map(lambda x: {'id': x['id'], 'streamUrl': x['stream_url'], 'status': x['status'],
                                'stats': x['statistic']}, parsed_jobs))

    volume = 'N/A'
    try:
        volume_info = subprocess.check_output(
            'sudo amixer sget Master|grep "%"|cut -d " " -f6|sed -e "s/\\[//" -e "s/\\]//"', shell=True)
        volume = volume_info.decode('utf8').split('\n')[0].strip()
    except Exception:
        pass
    free_space = 'N/A'
    try:
        free_space_info = subprocess.check_output(
            'df -h|grep "/$"|column -t|sed "s/  / /g"|cut -d " " -f5', shell=True)
        free_space = free_space_info.decode('utf8').strip()
    except Exception:
        pass

    try:
        cpu_name_info = subprocess.check_output(
            'df -h|grep "/$"|column -t|sed "s/  / /g"|cut -d " " -f5', shell=True)
        cpu_name = cpu_name_info.decode('utf8').strip()
    except Exception:
        cpu_name = 'N/A'

    try:
        ntls_info = subprocess.check_output(
            'cat /etc/findface-video-worker-cpu.ini |grep ntls_addr', shell=True)
        ntls = ntls_info.decode('utf8').strip().split('\n')[0].split('=')[1].strip()
    except Exception:
        ntls = 'N/A'

    try:
        shard_master_info = subprocess.check_output(
            'cat /etc/findface-sf-api.ini | grep master', shell=True)
        shard_master = shard_master_info.decode('utf8').strip().split('\n')[0].split('master:')[1].strip()
    except Exception:
        shard_master = 'N/A'

    ffmpeg_stats = []
    global dns_ip
    dns_ping_output = None
    if dns_ip is not None and len(dns_ip) > 0:
        try:
            dns_ping_output = subprocess.check_output('ping -c 5 {}'.format(dns_ip), shell=True).decode(
                'utf8').strip()
        except Exception as e:
            print(e)
            dns_ping_output = None

    client = tornado.httpclient.HTTPClient()
    try:
        t = get_cameras(client)
        cameras = json.loads(t.decode('utf8'))
        for camera in cameras:
            guid, link = camera['cameraGuid'], camera['cameraLink']
            try:
                url_parsed = urlparse(link)
                if url_parsed.scheme == 'file':
                    continue
                ping_output = subprocess.check_output('ping -c 5 {}'.format(url_parsed.hostname), shell=True).decode('utf8').strip()
            except Exception as e:
                print(e)
                ping_output = None
            ffmpeg_output = None
            try:
                ffmpeg_output = subprocess.check_output('ffmpeg -rtsp_transport tcp -i  \'{}\' -vcodec copy -an -y -t 10 test.mp4'.format(link), shell=True)
            except:
                pass
            if ffmpeg_output is None:
                try:
                    ffmpeg_output = subprocess.check_output('ffmpeg -rtsp_transport udp -i  \'{}\' -vcodec copy -an -y -t 10 test.mp4'.format(link), shell=True)
                except:
                    pass
            if ffmpeg_output is None:
                ffmpeg_stats.append({'guid': guid, 'link': link, 'ping': ping_output, 'status': 'failed'})
            else:
                try:
                    ffprobe_output = subprocess.check_output('ffprobe -v error -show_entries stream=width,height,bit_rate,r_frame_rate -of default=noprint_wrappers=1 test.mp4', shell=True)
                    ffprobe_stats = ffprobe_output.decode('utf8').strip().split('\n')
                    ffprobe_stats = dict(list(map(lambda x: x.split('='), ffprobe_stats)))
                    try:
                        ffprobe_stats['r_frame_rate'] = str(eval(ffprobe_stats['r_frame_rate']))
                    except:
                        pass
                    ffmpeg_stats.append({'guid': guid, 'link': link, 'ping': ping_output, 'status': 'success', 'stats': ffprobe_stats})
                except:
                    ffmpeg_stats.append({'guid': guid, 'link': link, 'ping': ping_output, 'status': 'failed'})
    finally:
        client.close()

    return {
        'loadavg': (avg1, avg2, avg3),
        'cpuCores': cpu_cores_count,
        'memory': memory_values,
        'swap': swap_values,
        'jobStats': stats,
        'streamStats': ffmpeg_stats,
        'uptime': uptime,
        'volume': volume,
        'freeSpace': free_space,
        'cpuName': cpu_name,
        'dnsPing': dns_ping_output,
        'ntls': ntls,
        'shardMaster': shard_master
    }


def get_and_send_stream_stats():
    stats = get_stats()
    stats['token'] = unlift_token
    print('STREAM STATS: ', stats)
    fetch_http_request(
        tornado.httpclient.HTTPRequest(
            url=post_proxy_stats_url,
            headers={"Content-Type": 'application/json', "Host": "unlift.ru"},
            body=json.dumps(stats),
            method='POST',
            follow_redirects=False,
            validate_cert=not disable_ssl),
    )


def get_roi_from_cam(camera, field):
    gpu_settings = camera.get('stream_settings_gpu')
    if gpu_settings is None:
        return None, None, None, None
    roi = gpu_settings.get(field)
    if len(roi) == 0:
        return None, None, None, None

    parsed = re.search('(\d+)x(\d+)\+(\d+)\+(\d+)', roi)
    if parsed is None:
        return None, None, None, None
    width, height, x, y = parsed.groups()
    width, height, x, y = int(width), int(height), int(x), int(y)
    return x, y, x + width, y + height


def get_roi_from_unlift(camera):
    left = None
    top = None
    right = None
    bottom = None
    for item in camera['roiSettings']:
        left = item['x1'] if left is None else min(left, item['x1'])
        top = item['y1'] if top is None else min(top, item['y1'])
        right = item['x2'] if right is None else max(right, item['x2'])
        bottom = item['y2'] if bottom is None else min(bottom, item['y2'])

    return left, top, right, bottom


def get_rot_from_unlift(camera):
    if camera['applyRotWithRoi']:
        return get_roi_from_unlift(camera)
    return None, None, None, None


def update_cameras():
    print("------------------update cameras-------------")
    global disable_ssl
    global min_score
    global min_face_size
    global max_face_size
    global monitoring
    client = tornado.httpclient.HTTPClient()
    try:
        result = client.fetch(
            tornado.httpclient.HTTPRequest(
                url="http://127.0.0.1:18810/jobs",
                method='GET',
                follow_redirects=False,
                request_timeout=get_request_timeout()))
        if result.error or not result.body:
            print('UPDATE CAMERAS ERROR: ' + str(result.error))
            return
        parsed = json.loads(result.body.decode('utf8'))
        current_cameras = set(
            map(lambda x: (x['id'], x['stream_url'], get_filter_settings(x), get_roi_from_cam(x, 'roi'), get_roi_from_cam(x, 'rot')), parsed))
        t = get_cameras(client)
        if monitoring:
            monitoring_min_score = -6 if min_score is None or min_score < 0 else 0
            new_cameras = set(map(lambda x: (x['cameraGuid'], x['cameraLink'], (monitoring_min_score, 30, 1000),
                                             (None, None, None, None), (None, None, None, None)), json.loads(t.decode('utf8'))))
        else:
            new_cameras = set(map(lambda x: (x['cameraGuid'], x['cameraLink'], (min_score, min_face_size, max_face_size),
                                             get_roi_from_unlift(x), get_rot_from_unlift(x)), json.loads(t.decode('utf8'))))
        print('CURRENT CAMERAS: {}'.format(str(current_cameras)))
        print('NEW CAMERAS: {}'.format(str(new_cameras)))
        if current_cameras == new_cameras:
            return
        for item in current_cameras.difference(new_cameras):
            client.fetch(
                tornado.httpclient.HTTPRequest(
                    url="http://127.0.0.1:18810/job/{}".format(item[0]),
                    method='DELETE',
                    follow_redirects=False,
                    request_timeout=2))
        for item in new_cameras.difference(current_cameras):
            body = {'stream_url': item[1]}
            if item[2] != (None, None, None):
                body['stream_settings_gpu'] = {}
                qual, min_f, max_f = item[2]
                if qual:
                    body['stream_settings_gpu']['filter_min_quality'] = qual
                if min_f:
                    body['stream_settings_gpu']['filter_min_face_size'] = min_f
                if max_f:
                    body['stream_settings_gpu']['filter_max_face_size'] = max_f

            if item[3] != (None, None, None, None):
                if 'stream_settings_gpu' not in body.keys():
                    body['stream_settings_gpu'] = {}
                left, top, right, bottom = item[3]
                body['stream_settings_gpu']['roi'] = '{}x{}+{}+{}'.format(right - left, bottom - top, left, top)
            if item[4] != (None, None, None, None):
                if 'stream_settings_gpu' not in body.keys():
                    body['stream_settings_gpu'] = {}
                left, top, right, bottom = item[4]
                body['stream_settings_gpu']['rot'] = '{}x{}+{}+{}'.format(right - left, bottom - top, left, top)

            client.fetch(
                tornado.httpclient.HTTPRequest(
                    url="http://127.0.0.1:18810/job/{}".format(item[0]),
                    method='POST',
                    body=json.dumps(body),
                    follow_redirects=False,
                    request_timeout=2))
    finally:
        client.close()


def send_camera_stat_record():
    global camera_stats_counter
    global disable_ssl
    global post_camera_stats_url
    print("------------------camera stats-------------")
    stats = camera_stats_counter.get_count()
    parsed_stats = list(map(lambda x: {'cameraGuid': x['cameraGuid'], 'facesCount': x['count'] - x['last_sent_count']},
                            stats))
    request_body = {'token': unlift_token, 'items': parsed_stats}
    full_photo_result = fetch_http_request(
        tornado.httpclient.HTTPRequest(
            url=post_camera_stats_url,
            headers={"Content-Type": 'application/json', "Host": "unlift.ru"},
            body=json.dumps(request_body),
            method='POST',
            follow_redirects=False,
            validate_cert=not disable_ssl,
            request_timeout=get_request_timeout()),
    )
    if full_photo_result.error is None:
        for item in stats:
            camera_stats_counter.set_last_sent_count(item['cameraGuid'], item['count'])


def get_store_tasks():
    print("------------------get store task-------------")
    global disable_ssl
    response = fetch_http_request(
        tornado.httpclient.HTTPRequest(
            url=url_concat(get_store_tasks_url, {'token': unlift_token, 'proxyVersion': proxy_version}),
            method='GET',
            headers={"Host": "unlift.ru"},
            follow_redirects=False,
            validate_cert=not disable_ssl,
            request_timeout=get_request_timeout()))
    on_get_tasks_response(response)


class IntervalThread(Thread):
    def __init__(self, func, interval, first_interval=None, event=Event()):
        Thread.__init__(self)
        self.interval = interval
        self.first_interval = first_interval
        self.should_use_first_interval = first_interval is not None
        self.func = func
        self.stopped = event

    def run(self):
        if self.should_use_first_interval and self.first_interval is not None and not self.stopped.wait(self.first_interval):
            try:
                self.func()
            except Exception as e:
                print('Thread exception: {}'.format(e))
                traceback.print_exc()
            finally:
                self.should_use_first_interval = False

        while not self.stopped.wait(self.interval):
            try:
                self.func()
            except Exception as e:
                print('Thread exception: {}'.format(e))
                traceback.print_exc()


def encode_multipart_formdata(fields, files, boundary=None):
    """
    fields is a sequence of (name, value) elements for regular form fields.
    files is a sequence of (name, filename, value) elements for data to be
    uploaded as files.
    Return (content_type, body) ready for httplib.HTTP instance
    """

    validated_boundary = boundary if boundary else '----------ThIs_Is_tHe_bouNdaRY_$'
    l = []
    for item in fields:
        key, value = item[0], item[1]
        l.append('--' + validated_boundary)
        l.append('Content-Disposition: form-data; name="%s"' % key)
        if len(item) > 2:
            l.append('Content-Type: {}'.format(item[2]))
        l.append('')
        if value is str:
            l.append(value)
        else:
            l.append(str(value).encode('utf8'))
    for file in files:
        key, filename, value = file
        l.append('--' + validated_boundary)
        l.append(
            'Content-Disposition: form-data; name="%s"; filename="%s"' % (
                key, filename
            )
        )
        l.append('Content-Type: %s' % get_content_type(filename))
        l.append('')
        l.append(bytearray(value))
    l.append('--' + validated_boundary + '--')
    l.append('')

    result = []
    for item in l:
        if type(item) is str:
            result.append(bytearray(item, 'utf8'))
        else:
            result.append(item)
    body = bytearray('\r\n', 'utf8').join(result)
    body = bytes(body)
    content_type = 'multipart/form-data; boundary=%s' % validated_boundary
    return content_type, body


def get_content_type(filename):
    return mimetypes.guess_type(filename)[0] or 'application/octet-stream'


def on_visit_sent(response, face_id, start_time, confidence, gender):
    request_time = time.time() - start_time
    print("---- sending register visitFace finished in {} faceId={} confidence={} ----".format(request_time, face_id, confidence))
    print("---- visitFace response ----")
    try:
        parsed_body = json.loads(response.body.decode('utf8'))
        print_escaped(parsed_body)
        data = parsed_body.get('data')
        if data is not None:
            global overseer_threshold
            if overseer_threshold is None or confidence > overseer_threshold:
                relationship_type = data.get('globalRelationshipType')
                # try:
                #     # if relationship_type == 0:
                #     #     play_sound('warning', face_id, gender)
                #     # elif relationship_type == 1:
                #     #     play_sound('notice', face_id, gender)
                # except Exception:
                #     pass
    except Exception as e:
        print(e)
    print("/---- visitFace response ----")


def send_visit(image, data, face_id, confidence, gender, raw_image, age, top, bottom, left, right):
    content_type, body = encode_multipart_formdata(data, [image])
    global disable_ssl
    global post_face_visit_url
    current_time = time.time()
    response = fetch_http_request(
        tornado.httpclient.HTTPRequest(
            url=post_face_visit_url,
            method="POST",
            body=body,
            headers={"Content-Type": content_type, 'content-length': str(len(body)), "Host": "unlift.ru"},
            follow_redirects=False,
            request_timeout=120,
            validate_cert=not disable_ssl))
    on_visit_sent(response, face_id, current_time, confidence, gender)
    if confidence is None:
        return
    parsed_body = json.loads(response.body.decode('utf8'))
    response_data = parsed_body.get('data')
    if response_data is None:
        print('SENDING ALARM VISIT PREVENTED DUE TO NULL RESULT')
        return
    ignore_notifications = response_data.get('ignoreNotifications', False)
    if not ignore_notifications:
        try:
            send_visit_to_alarm(raw_image, face_id, confidence, gender, age, top, bottom, left, right, response)
        except Exception as e:
            print('SENDING ALARM VISIT FAILED WITH: {}'.format(e))
    else:
        print('SENDING ALARM VISIT PREVENTED DUE TO PERSON SETTINGS')


def get_confidence_description(confidence):
    if confidence > 0.7834:
        return 'высокое'
    if confidence < 0.77:
        return 'низкое'
    return ''


def send_visit_to_alarm(image, face_id, confidence, gender, age, top, bottom, left, right, response):
    parsed_body = json.loads(response.body.decode('utf8'))
    print(parsed_body)
    data = parsed_body.get('data')
    relationship_type = data.get('globalRelationshipType')
    person_id = data.get('id')
    first_name = data.get('firstName')
    last_name = data.get('lastName')
    patronymic = data.get('patronymic')
    incidents_count = data.get('incidentsCount')
    visit_id = data.get('visitId')
    camera_description = data.get('cameraDescription')
    stolen_goods_types = data.get('stolenGoodsTypes')
    is_self_checkout = data.get('isSelfCheckout', False)
    should_render_full_frame = data.get('shouldRenderFullFrame', False)

    global overseer_threshold
    request_data = {
        'id': visit_id,
        'confidence': confidence,
        'isRecidivist': incidents_count > 1,
        'relationshipType': relationship_type,
        'personId': person_id,
        'faceId': face_id,
        'firstName': first_name,
        'lastName': last_name,
        'patronymic': patronymic,
        'age': str(age),
        'gender': gender,
        'emotion': '',
        'confidenceThreshold': overseer_threshold,
        'confidenceDescription': get_confidence_description(confidence),
        'cameraDescription': camera_description,
        'stolenGoodsTypes': stolen_goods_types,
        'isSelfCheckout': is_self_checkout,
        'shouldRenderFullFrame': should_render_full_frame
    }
    print('VISIT ALARM DEBUG', json.dumps(request_data))
    request_data['capturedFace'] = {
        'photo': base64.b64encode(image).decode('utf-8'),
        'bbox': {
            'top': top,
            'bottom': bottom,
            'left': left,
            'right': right
        }
    }
    request_data['matchedFace'] = None
    # request_data['matchedFace'] = {
    #     'photo': base64.b64encode(image).decode('utf-8'),
    #     'bbox': {
    #         'top': top,
    #         'bottom': bottom,
    #         'left': left,
    #         'right': right
    #     }
    # }

    fetch_http_request(tornado.httpclient.HTTPRequest(
        url='http://localhost:5477/visit',
        method="POST",
        body=json.dumps(request_data),
        headers={"Content-Type": 'application/json'},
        follow_redirects=False,
        request_timeout=1,
    ))


cameras_guids = []


def get_camera_number(camera_guid):
    print(cameras_guids)
    if camera_guid in cameras_guids:
        return cameras_guids.index(camera_guid)
    return -1


def store_face(cropped_img, score, direction_score,
               last_meta, last_k, camera_guid, x1, y1, x2, y2, face_time, gender, age, emotion):
    global min_score
    global min_direction_score
    if min_score and score != 0 and score < min_score or min_direction_score and direction_score != 0 and abs(
            direction_score) > min_direction_score:
        print('storeFace: face is too bad to store')
        return
    print('---- validate roi ----')
    global cameras_settings
    if cameras_settings is not None:
        print('trying verify roi')
        current_camera_settings = next(filter(lambda x: x["cameraGuid"] == camera_guid, cameras_settings), None)
        face = Rectangle(x1, y1, x2, y2)
        min_intersection_square = (x2 - x1) * (y2 - y1) * 0.5
        print('min intersection is {}'.format(min_intersection_square))
        print(cameras_settings)
        print(camera_guid)
        print(current_camera_settings)
        if current_camera_settings and current_camera_settings['roiSettings']:
            is_valid = False
            for item in current_camera_settings['roiSettings']:
                zone = Rectangle(item["x1"], item["y1"], item["x2"], item["y2"])
                square = area(face, zone)
                if square and square >= min_intersection_square:
                    is_valid = True
                    print('intersection square is {}, valid'.format(square))
                    break
            if not is_valid:
                print('face not in roi')
                return
    global face_verify_timespan
    try:
        save_photo(cropped_img, score, direction_score, last_meta,
                   last_k, camera_guid, x1, y1, x2, y2, face_time, gender, age, emotion)
    except Exception as e:
        print('store face to db error')
        print(e)


def should_send_full_photo(face_id):
    if not face_id:
        return False, False
    global disable_ssl
    try:
        full_photo_result = fetch_http_request(
            tornado.httpclient.HTTPRequest(
                url=url_concat(send_full_url, {'token': unlift_token, 'faceId': face_id}),
                method='GET',
                headers={"Host": "unlift.ru"},
                follow_redirects=False,
                validate_cert=not disable_ssl)
        )
        if full_photo_result.error is not None or full_photo_result.body is None:
            return True, True
        parsed = json.loads(full_photo_result.body.decode('utf8'))
        if 'data' in parsed.keys():
            return parsed['data']['shouldSendFull'], parsed['data']['shouldSend']
        else:
            return True, True
    except Exception as e:
        print('send full error: {}'.format(e))
        return True, True


class ForwardingRequestHandler(tornado.web.RequestHandler):
    def data_received(self, chunk):
        pass

    listeners = {}
    executor = ThreadPoolExecutor(max_workers=os.cpu_count())
    camera_string = None
    cameras = []

    @tornado.web.asynchronous
    def post(self):
        print("{0}: {1} {2} request. Forwarding post to FFServer..\n\n".format(datetime.datetime.now(),
                                                                               self.request.method, self.request.uri))
        face_time = time.time()
        if self.request.uri == "/v2/face":
            print("and it's received!!!!!!!!!!!!!!!!!!!!")
            self.set_status(200)
            self.finish()
            global is_recognition_enabled
            if not is_recognition_enabled:
                print('----recognition disabled, skipped----')
                self.set_status(500)
                self.write("Recognition disabled on unlift sever")
                self.finish()
                return
            args = {}
            files = {}
            content_type = self.request.headers.get("Content-Type")
            tornado.httputil.parse_body_arguments(content_type, self.request.body, args,
                                                  files)
            print(args)
            video_frame = files["photo"][0]["body"]
            detector_params = json.loads(args["detectorParams"][0].decode('utf8'))
            score = detector_params.get('score', detector_params.get('quality', 0))
            direction_score = detector_params.get('direction_score', 0)
            img = Image.open(BytesIO(video_frame))
            x1 = int(args['x1'][0].decode('utf8'))
            x2 = int(args['x2'][0].decode('utf8'))
            y1 = int(args['y1'][0].decode('utf8'))
            y2 = int(args['y2'][0].decode('utf8'))
            features = json.loads(args['features'][0].decode('utf8'))
            gender, age, emotion = None, None, None
            if features:
                gender = features.get('gender', None)
                if gender:
                    gender = gender.get('gender', None)
                age = features.get('age', None)
                if age:
                    age = int(round(age))
                emotions = features.get('emotions', None)
                if emotions:
                    emotion = emotions[0].get('emotion', None)
            print(gender, age, emotion)
            cropped_img = crop_face(img, x1, x2, y1, y2, True)
            img_byte_arr = BytesIO()
            cropped_img.save(img_byte_arr, format='JPEG')

            cam_id = args['cam_id'][0].decode('utf8').strip("\"")
            global camera_stats_counter
            camera_stats_counter.increase(cam_id)
            print(args)
            global threshold
            frame_img_arr = BytesIO()
            img.save(frame_img_arr, format='JPEG')
            frame_img_arr = frame_img_arr.getvalue()
            identify_result = json.loads(args['identify_result'][0].decode('utf8'))
            print(identify_result)
            face_id = identify_result.get('id', None)
            confidence = identify_result.get('confidence', None)
            print('threshold is ' + str(threshold) + ' and confidence is ' + str(confidence))
            if threshold is not None and confidence is not None and (confidence < threshold):
                face_id = None
                confidence = None
            print('now threshold is ' + str(threshold) + ' and confidence is ' + str(confidence))
            should_send_full, should_send = should_send_full_photo(face_id)
            if face_id and should_send and (threshold is None or (confidence is not None and (confidence >= threshold))):
                try:
                    if should_send_full:
                        file = ('file', 'image.jpg', frame_img_arr)
                        data = [("token", unlift_token), ("id", face_id), ("k", confidence), ("x1", x1), ("y1", y1),
                                ("x2", x2), ("y2", y2), ("cameraGuid", cam_id)]
                    else:
                        file = ('file', 'image.jpg', img_byte_arr.getvalue())
                        width = x2 - x1
                        height = y2 - y1
                        ext_x1 = x1 - int(round(0.5 * width))
                        ext_y1 = y1 - int(round(0.5 * height))
                        data = [("token", unlift_token), ("id", face_id), ("k", confidence), ("x1", x1 - ext_x1),
                                ("y1", y1 - ext_y1),
                                ("x2", width + x1 - ext_x1), ("y2", height + y1 - ext_y1),
                                ("cameraGuid", cam_id)]
                    print(
                        "{0}: ---- sending register visitFace request faceId={1} sinceDetected={2} confidence={3} ----".format(
                            datetime.datetime.now(), face_id, time.time() - face_time, confidence))

                    print(data)

                    send_visit(file, data, face_id, confidence, gender, frame_img_arr, age, y1, y2, x1, x2)
                    print("/---- visitFace ----")
                except Exception as e:
                    print("Error: " + str(e))
            else:
                try:
                    if monitoring:
                        print("-------------------- monitoring new face -------------------------")
                        data = [("token", unlift_token), ("x1", x1), ("y1", y1),
                                ("x2", x2), ("y2", y2), ("cameraGuid", cam_id)]
                        print(data)
                        file = ('file', 'image.jpg', frame_img_arr)
                        send_visit(file, data, None, None, None, None, None, None, None, None, None)
                        print("/---- monitoringFace ----")
                        print("-------------------------------------------------------")
                    else:
                        print(monitoring)
                        print(" no monitoring face ")
                except Exception as e:
                    # Other errors are possible, such as IOError.
                    print("Error: " + str(e))
            if save_detect:
                store_face(cropped_img, score, direction_score,
                           face_id, confidence, cam_id, x1, y1, x2, y2, face_time, gender, age, emotion)
        else:
            self.set_status(200)
            self.finish()


def make_app():
    db = motor.motor_tornado.MotorClient().video
    return tornado.web.Application([
        (r"/.*", ForwardingRequestHandler),
    ], debug=True, db=db)


def main(argv):
    config_file_path = None
    try:
        opts, args = getopt.getopt(argv, "hc:")
    except getopt.GetoptError:
        print('unlift.py -c <configfile>')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('unlift.py -c <configfile>')
            sys.exit()
        elif opt in "-c":
            config_file_path = arg
    return config_file_path


def start_daemon_thread(func, interval, first_interval=None):
    daemon_thread = IntervalThread(func, interval, first_interval)
    daemon_thread.daemon = True
    daemon_thread.start()


def start_subproccess(args):
    print('SUBPROCESS STARTED WITH ARGS: {}'.format(str(args)))
    try:
        subprocess.run(args)
    except:
        print("Subprocess failed, args={} error={}".format(str(args), str(db_client_e)))


def play_sound(sound_type, person_id, gender):
    print('SOUND PLAYING: STARTED, TYPE: {}, PERSON_ID: {}'.format(sound_type, person_id))
    global should_play_sound
    global visits_time_list
    global last_staff_playing_time
    global last_incident_playing_time
    global incident_music_interval
    global staff_music_interval
    global must_ignore_stuff_timer
    global must_play_on_incident
    global must_play_on_stuff
    global must_play_differ_sounds_by_gender

    utcnow = datetime.datetime.utcnow()
    if not should_play_sound:
        print('SOUND PLAYING: DISABLED')
        return
    last_time = visits_time_list.get_time(person_id)
    last_category_playing_time = None
    if sound_type == 'warning' and must_ignore_stuff_timer:
        last_category_playing_time = last_incident_playing_time
    else:
        date_items = []
        if last_staff_playing_time is not None:
            date_items.append(last_staff_playing_time)
        if last_incident_playing_time is not None:
            date_items.append(last_incident_playing_time)
        if len(date_items) > 0:
            last_category_playing_time = max(date_items)

    playing_interval = 600
    if sound_type == 'warning':
        if not must_play_on_incident:
            print('SOUND PLAYING: INCIDENT PLAYING DISABLED')
            return
        playing_interval = incident_music_interval
    elif sound_type == 'notice':
        playing_interval = staff_music_interval
        if not must_play_on_stuff:
            print('SOUND PLAYING: STAFF PLAYING DISABLED')
            return
    if last_time is not None and (utcnow - last_time).seconds < (60 * 60) or last_category_playing_time is not None and (utcnow - last_category_playing_time).seconds < playing_interval:
        print('SOUND PLAYING: SKIPPED, TOO OFTEN, TYPE: {}, PERSON_ID: {}, this person last time: {}, general last time: {}'.format(sound_type, person_id, str(last_time), str(last_category_playing_time)))
        return
    if sound_type == 'warning' and not must_play_differ_sounds_by_gender:
        last_incident_playing_time = utcnow
        filename = 'warning.mp3'
    elif sound_type == 'warning':
        if gender == 'female' or gender == 'FEMALE':
            filename = 'warningf.mp3'
        else:
            filename = 'warning.mp3'
    elif sound_type == 'notice':
        last_staff_playing_time = utcnow
        filename = 'notice.mp3'
    else:
        return

    sound_lock = 'sound.lock'
    try:
        with open(sound_lock, 'x'):
            pass
    except:
        print('SOUND PLAYING: PREVENTED, SOUND LOCK EXISTS')
        return
    try:

        sound_thread = threading.Thread(target=start_subproccess, args=(["ffplay", "-nodisp", "-autoexit", filename],))
        sound_thread.start()
        print('SOUND PLAYING: EXECUTED, TYPE: {}, PERSON_ID: {}'.format(sound_type, person_id))
        visits_time_list.update_time(person_id)
    except Exception as e:
        print("Playing sound error: {}".format(str(e)))
    try:
        os.remove(sound_lock)
    except:
        print('SOUND PLAYING: SOUND LOCK REMOVING FAILED')


if __name__ == "__main__":
    configfile = main(sys.argv[1:])
    print('Config file is "', configfile)
    print("==== Settings ====")
    config = configparser.ConfigParser()
    config.read(configfile)
    port = config['General']['port']
    disable_ssl = True if config['General'].get('disable_ssl', None) == 'True' else False
    unlift_host = 'unlift.ru' if not disable_ssl else '185.158.114.149'
    db_path = 'unlift_face.db'
    extended_face = config['General'].getboolean('extended_face')
    unlift_token = config['General']['unlift_token']
    pingUrl = "https://{}/api/stores/ping".format(unlift_host)
    get_store_tasks_url = "https://{}/api/stores/getTasks".format(unlift_host)
    unlift_log_url = "https://{}/api/proxy/addProxyLogItems".format(unlift_host)
    send_full_url = "https://{}/api/proxy/shouldSendFull".format(unlift_host)
    upload_faces_url = "https://{}/api/stores/uploadFaces".format(unlift_host)
    post_camera_stats_url = "https://{}/api/stores/cameraStats".format(unlift_host)
    post_proxy_stats_url = "https://{}/api/proxy/proxyStats".format(unlift_host)
    post_face_visit_url = "https://{}/api/person/visitFace".format(unlift_host)
    get_cameras_url = "https://{}/api/proxy/cameras?v=2&token={}".format(unlift_host, unlift_token)
    finish_play_test_sound_url = "https://{}/api/proxy/finishTestSoundTask".format(unlift_host)
    monitoring = False
    is_recognition_enabled = True
    proxy_version = '2.2.20.2a'
    must_play_on_incident = True
    must_play_on_stuff = True
    must_play_differ_sounds_by_gender = True
    must_ignore_stuff_timer = False
    incident_music_interval = 600
    staff_music_interval = 600
    min_score = None
    min_direction_score = None
    min_face_size = None
    max_face_size = None
    save_detect = False
    face_verify_timespan = 15
    threshold = 0.75
    overseer_threshold = None
    cameras_settings = None
    visits_time_list = VisitTimeList()
    last_staff_playing_time = None
    last_incident_playing_time = None
    dns_ip = None
    ping_error_counter = FaceCounter()
    db_client = sqlite3.connect(db_path)
    try:
        create_db(db_client)
    except Exception as db_client_e:
        print(db_client_e)
    print("* port = " + port)
    print("* unlift_token = " + unlift_token)
    print("* db_path = " + db_path)
    print("* disable_ssl = " + str(disable_ssl))
    print("* base_host = " + unlift_host)
    print("//== Settings ====")
    camera_stats_counter = CameraStatsCounter()
    start_daemon_thread(send_ping_request, 60)
    start_daemon_thread(send_camera_stat_record, 60)
    start_daemon_thread(update_cameras, 60)
    start_daemon_thread(upload_stats, 60)
    start_daemon_thread(get_store_tasks, 10)
    start_daemon_thread(run_tasks, 30)
    start_daemon_thread(get_and_send_stream_stats, 3600, 300)
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
