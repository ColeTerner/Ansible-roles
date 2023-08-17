#!/usr/bin/python3
import configparser
import getopt
import json

import sys
import zipfile
from threading import Event

import tornado.httpclient
import tornado.escape
from io import BytesIO
from tornado.httputil import url_concat


def update_config(version):
    config.set('General', 'CurrentVersion', version)
    with open(config_file_path, 'w') as config_file:
        config.write(config_file)


def update_proxy(update_url, latest_version):
    http_client = tornado.httpclient.HTTPClient()
    global disable_ssl
    response = http_client.fetch(
        tornado.httpclient.HTTPRequest(
            url=update_url,
            method='GET',
            headers={"Host": "unlift.ru"},
            follow_redirects=False,
            validate_cert=not disable_ssl))

    if response.error:
        print(response.error)
        return
    print('Update downloaded, copying to {}'.format(proxy_path))
    zip_ref = zipfile.ZipFile(BytesIO(response.body), 'r')
    zip_ref.extractall(proxy_path)
    zip_ref.close()
    print('Update copied to {}, updating latest version in config'.format(proxy_path))
    try:
        update_config(latest_version)
    except Exception as config_e:
        print('Config updating is failed: {}'.format(config_e))
    global current_version
    current_version = latest_version
    print('Config updated, current version is {}'.format(current_version))


def check_update():
    http_client = tornado.httpclient.HTTPClient()
    print('Update checking started')
    global disable_ssl
    response = http_client.fetch(
        tornado.httpclient.HTTPRequest(
            url=url_concat(unlift_url, {'token': unlift_token, 'supportPackages': True, 'packageId': package_id}),
            method='GET',
            headers={"Host": "unlift.ru"},
            follow_redirects=False,
            validate_cert=not disable_ssl))

    if response.error:
        print(response.error)
        return
    parsed_body = json.loads(tornado.escape.to_unicode(response.body))
    latest_version = parsed_body['data']['latest']
    print('Latest version is {}'.format(latest_version))
    if latest_version and latest_version != current_version:
        print('Current version is {}, updating started'.format(current_version))
        update_proxy(parsed_body['data']['url'], latest_version)


def get_config_path(argv):
    try:
        opts, args = getopt.getopt(argv, "hc:")
    except getopt.GetoptError:
        print('updater.py -c <configfile>')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('updater.py -c <configfile>')
            sys.exit()
        elif opt in "-c":
            return arg


if __name__ == "__main__":
    stopped = Event()
    config_file_path = get_config_path(sys.argv[1:])
    print('Config file is "', config_file_path)
    print("==== Settings ====")
    config = configparser.ConfigParser()
    config.read(config_file_path)
    proxy_path = config['General']['ProxyPath']
    unlift_url = config['General']['UpdateUrl']
    interval = int(config['General']['Interval'])
    unlift_token = config['General']['UnliftToken']
    current_version = config['General']['CurrentVersion']
    package_id = config['General']['PackageId']
    disable_ssl = True if config['General'].get('disable_ssl', None) == 'True' else False
    print("* ProxyPath = " + proxy_path)
    print("* UpdateUrl = " + unlift_url)
    print("* Interval = " + str(interval))
    print("* UnliftToken = " + unlift_token)
    print("* CurrentVersion = " + current_version)
    print("* disable_ssl = " + str(disable_ssl))
    while not stopped.wait(interval):
        try:
            check_update()
        except Exception as e:
            print(e)
