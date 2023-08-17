import configparser
import getopt
import sqlite3
import json
import sys
import tornado.escape
import datetime
import time
from io import BytesIO
from ff_api import FindFaceApiClient


def log(text):
    try:
        print(text)
        current_date = datetime.datetime.utcnow()
        with open('unlift_stats.log', 'a') as detect_log:
            detect_log.write(';'.join([str(current_date), str(text)]) + '\n')
    except:
        pass


# noinspection SqlNoDataSourceInspection,SqlResolve
class UnliftStats:
    def __init__(self, _db_path, _ff_client: FindFaceApiClient = None):
        self._ff_client = _ff_client
        self._sqlite_client = sqlite3.connect(_db_path)
        self.create_db()

    def create_db(self):
        self._sqlite_client.execute("""
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
        self._sqlite_client.execute("""
CREATE TABLE IF NOT EXISTS proxy_log_record (
id INTEGER PRIMARY KEY AUTOINCREMENT,
file_id INTEGER NOT NULL, 
age TEXT NULL,
emotion TEXT NULL,
gender TEXT NULL,
similar_to INTEGER NULL,
FOREIGN KEY (file_id) REFERENCES proxy_file(id) ON DELETE CASCADE,
FOREIGN KEY (similar_to) REFERENCES proxy_file(id) ON DELETE SET NULL)""")
        self._sqlite_client.commit()

    def add_fails_counter(self, item_id):
        try:
            self._sqlite_client.execute("""UPDATE proxy_file SET fails = fails + 1 WHERE id = ?""", item_id)
            self._sqlite_client.commit()
        except Exception as e:
            log(e)

    def __on_detect_response__(self, response, item_id):
        if response.body:
            result = json.loads(tornado.escape.to_unicode(response.body))
            log(result)
            face = next(iter(result.get('faces', [])), {'gender': 'error', 'emotions': ['failed'], 'age': 0})
        else:
            self.add_fails_counter(item_id)
            return
        gender = face.get("gender")
        if gender == 'male':
            gender = 'm'
        elif gender == 'female':
            gender = 'f'
        else:
            gender = 'e'
        emotion = face.get('emotions', ['failed'])[0]
        age = int(round(face.get('age')))
        self._sqlite_client.execute("""
INSERT INTO proxy_log_record (file_id, age, emotion, gender)
VALUES (?, ?, ?, ?)""", (item_id, age, emotion, gender))
        self._sqlite_client.commit()

    def verify_with_previous(self, item):
        log('trying verify')
        log(item)
        item_id, path, file_time = item
        global verify_span
        time_start = file_time - verify_span * 1000
        cursor = self._sqlite_client.cursor()
        cursor.execute("""
SELECT proxy_file.id, proxy_file.path, proxy_file.datetime FROM proxy_file 
WHERE proxy_file.id != ? AND proxy_file.datetime >= ?
AND proxy_file.datetime < ? LIMIT 10000""", (item_id, time_start, file_time))
        results = cursor.fetchall()
        log('previous faces')
        log(results)
        for other in results:
            try:
                self.verify(item, other)
            except Exception as e:
                log(e)
            time.sleep(3)

    def detect(self, item):
        item_id, path, file_time = item
        try:
            with open(path, mode='rb') as face_file:
                img_bytes = BytesIO(face_file.read()).getvalue()
            self.__on_detect_response__(self._ff_client.detect(img_bytes), item_id)
            self.verify_with_previous(item)
        except Exception as e:
            log(e)
            self.add_fails_counter(item_id)

    def start_process(self):
        cursor = self._sqlite_client.cursor()
        cursor.execute("""
SELECT proxy_file.id, proxy_file.path, proxy_file.datetime FROM proxy_file 
LEFT JOIN proxy_log_record ON proxy_log_record.file_id = proxy_file.id
WHERE proxy_log_record.id IS NULL AND fails < 5 ORDER BY proxy_file.datetime LIMIT 10000""")
        results = cursor.fetchall()
        for item in results:
            log('trying process {}'.format(item[1]))
            self.detect(item)
            time.sleep(3)

    def verify(self, item1, item2):
        item1_id, path1, _ = item1
        item2_id, path2, _ = item2
        with open(path1, mode='rb') as file1, open(path2, mode='rb') as file2:
            file1_bytes, file2_bytes = BytesIO(file1.read()).getvalue(), BytesIO(file2.read()).getvalue()
            response = self._ff_client.verify(file1_bytes, file2_bytes)
        if response and response.error is None:
            body = json.loads(tornado.escape.to_unicode(response.body))
            log(body)
            if body.get("verified", False):
                self._sqlite_client.execute("""UPDATE proxy_log_record SET similar_to = ? WHERE file_id = ?""",
                                            (item1_id, item2_id))
                self._sqlite_client.commit()

    def add_file(self, path, score, dir_score, width, height, x, y, camera_id, file_datetime, face_id, confidence):
        int_time = int(file_datetime * 1000)
        self._sqlite_client.execute("""
INSERT INTO proxy_file (path, score, dir_score, width, height, x, y, camera_id, datetime, face_id, confidence)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (path, score, dir_score, width, height, x, y, camera_id, int_time, face_id, confidence))
        self._sqlite_client.commit()


def main(argv):
    config_file_path = None
    try:
        opts, args = getopt.getopt(argv, "hc:")
    except getopt.GetoptError:
        print('unlift_stats.py -c <configfile>')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('unlift_stats.py -c <configfile>')
            sys.exit()
        elif opt in "-c":
            config_file_path = arg
    return config_file_path


if __name__ == "__main__":
    configfile = main(sys.argv[1:])
    config = configparser.ConfigParser()
    config.read(configfile)
    log('Starting unlift statistics...')
    log('Config file is {}'.format(configfile))
    log("==== Settings ====")
    host = config['General']['host']
    port = config['General']['port']
    token = config['General']['token']
    unlift_token = config['General']['unlift_token']
    db_path = config['General']['db_path']
    log("* host = " + host)
    log("* port = " + port)
    log("* token = " + token)
    log("* unlift_token = " + unlift_token)
    log("* db_path = " + db_path)
    log("//== Settings ====")
    ff_client = FindFaceApiClient(host, port, token)
    verify_span = 15
    stats_client = UnliftStats(db_path, ff_client)
    stats_client.start_process()
