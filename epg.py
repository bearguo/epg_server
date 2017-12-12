import configparser
import html
import threading
from contextlib import contextmanager
from logging.handlers import TimedRotatingFileHandler
from flask import (
    Flask,
    request,
    make_response
)
from flask_cors import CORS
import logging
from urllib.request import urlopen
from urllib.parse import urljoin, urlencode, urlparse
import wrapcache
from pathlib import Path
import os, sys
from xml.etree import ElementTree as et
from retry import retry
import time


if getattr(sys, 'frozen', False):
    cur_path = os.path.dirname(sys.executable)
elif __file__:
    cur_path = os.path.dirname(os.path.realpath(__file__))
log_file_name = str(Path(cur_path) / 'epg.log')
log_file_handler = TimedRotatingFileHandler(filename=log_file_name, when="D", interval=1, backupCount=3)
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s %(message)s',
                    handlers=[log_file_handler]
                    )
logging.info('log file created!')
PORT = 10010
try:
    cf = configparser.ConfigParser()
    cf.read(str(Path(cur_path) / 'epg.conf'))
    THIRD_PARTY_EPG_URL_BASE = cf.get('epg_master', 'base_url')
    PORT = cf.get('server', 'port')
    logging.info('epg slave port is %s' % PORT)
    logging.info('epg master url is: %s' % THIRD_PARTY_EPG_URL_BASE)
except Exception as e:
    logging.exception('Parse configuration file failed!')
    sys.exit(-1)

app = Flask('__name__')
CORS(app)
SECRET_KEY = 'VYDcCe1s'
NEW_DATA_SIGN = '1'
OLD_DATA_SIGN = '0'
MIN_XML_LENGTH = 200
schedule_cache_dict = {}
channel_cache = None
mutex = threading.Lock()
global cur_time
# debug_counter = 0


def string_to_html(string):
    string = html.escape(str(string))
    return """<!DOCTYPE html>
<html lang='en'>
<head>
    <meta charset="UTF-8">
    <title>EPG Master Server Error</title>
</head>
<body>
%s
</body>
</html>""" % string


@wrapcache.wrapcache(timeout=5 * 60)
def get_schedule_xml(url: str):
    # global debug_counter
    # debug_counter += 1
    # print("in get schedule xml function!", debug_counter)
    web_page = urlopen(url, timeout=5).read()
    return web_page


@wrapcache.wrapcache(timeout=12 * 60 * 60)
def get_channel_xml(url: str):
    # global debug_counter
    # debug_counter += 1
    # print("in get channel xml function!", debug_counter)
    web_page = urlopen(url, timeout=5).read()
    return web_page


@app.route('/EPG/channel', methods=['GET'])
def channel():
    """
    Cache the 3rd party epg server channel api.

    :return: xml page from 3rd party epg server.
    """
    # 1. Check the secret key value.
    secret_key = request.args.get('secret', None)
    if secret_key is None:
        error_message = 'missing the secret key! please check the url!'
        logging.error(error_message)
        return error_message
    elif secret_key != SECRET_KEY:
        error_message = 'wrong secret key!'
        logging.error(error_message)
        return error_message

    rsp = make_response(channel_cache)
    rsp.mimetype = 'text/xml'
    return rsp


@app.route('/EPG/schedule')
def schedule():
    # 1. Check the secret key value.
    secret_key = request.args.get('secret', None)
    if secret_key is None:
        error_message = 'missing the secret key! please check the url!'
        logging.error(error_message)
        return error_message
    elif secret_key != SECRET_KEY:
        error_message = 'wrong secret key!'
        logging.error(error_message)
        return error_message

    # 2. Check the id
    channel_id = request.args.get('id', None)
    if channel_id is None:
        error_message = 'missing the id key! please check the url!'
        logging.error(error_message)
        return error_message
    elif channel_id not in schedule_cache_dict:
        error_message = 'wrong channel id! please check the id!'
        logging.error(error_message)
        return error_message
    rsp = make_response(schedule_cache_dict.get(channel_id))
    rsp.mimetype = 'text/xml'
    return rsp


def refresh_caches():
    """
    Refresh the cache in the memory for every 24 hours.

    :return: None
    """
    while 1:
        global schedule_cache_dict
        wrapcache.flush()
        schedule_cache_dict = {}
        time.sleep(24 * 60 * 60)


@contextmanager
def acquire_timeout(lock, timeout):
    result = lock.acquire(timeout=timeout)
    yield result
    if result:
        lock.release()


def lock_decorator(func):
    def wrapper(*args, **kwargs):
        result = None
        with acquire_timeout(mutex, timeout=3) as acquired:
            if acquired:
                result = func(*args, **kwargs)
        return result
    return wrapper


@retry(Exception, tries=5, delay=1, backoff=2)
def fetch_schedule_xml(channel_id):
    """
    获取某个频道的最近2周节目信息

    数据格式：
    <?xml version="1.0" encoding="UTF-8"?>
    <document>
    <schedule channel_id="CCTV1" epg_code="CCTV1" date="2017-12-07">
        <event id="819390800">
            <start_time>00:16</start_time>
            <end_time>00:27</end_time>
            <title><![CDATA[生活提示]]></title>
        </event>
        <event id="819390805">
            <start_time>00:27</start_time>
            <end_time>02:06</end_time>
            <title><![CDATA[魅力中国城]]></title>
        </event>
    </schedule>
    </document>
    """
    # return """    <document>
    # <schedule channel_id="CCTV1" epg_code="CCTV1" date="2017-12-07">
    #     <event id="819390800">
    #         <start_time>00:16</start_time>
    #         <end_time>00:27</end_time>
    #         <title><![CDATA[生活提示]]></title>
    #     </event>
    #     <event id="819390805">
    #         <start_time>00:27</start_time>
    #         <end_time>02:06</end_time>
    #         <title><![CDATA[魅力中国城]]></title>
    #     </event>
    # </schedule>
    # </document>"""
    print('Enter channel:%s'%channel_id)
    params = {
        'secret': SECRET_KEY,
        'id': channel_id
    }
    url = '%s/%s?%s' % (THIRD_PARTY_EPG_URL_BASE, 'schedule', urlencode(params))
    try:
        web_page = urlopen(url, timeout=10).read()
    except Exception as e:
        logging.error('Fetch schedule xml failed. %s' % url)
        logging.exception(e)
        return None
    return web_page

@retry(Exception, tries=5, delay=1, backoff=2)
def fetch_channel_xml():
    """
    获取所有频道列表

    数据格式：
    <?xml version="1.0" encoding="UTF-8"?>
    <document>
        <channel id="AHTV1">
            <logo>
                <![CDATA[
                http://img.tvmao.com/images/logo/channel/AHTV1/AHTV1_140x140.png
                ]]>
            </logo>
            <name>
                <![CDATA[ 安徽卫视 ]]>
            </name>
        </channel>
        <channel id="BTV1">
            <logo>
                <![CDATA[
                http://img.tvmao.com/images/logo/channel/BTV1/BTV1_140x140.png
                ]]>
            </logo>
            <name>
                <![CDATA[ 北京卫视 ]]>
            </name>
        </channel>
    </document>
    """
    # return """<document>
    #     <channel id="CCTV1">
    #         <logo>
    #             <![CDATA[
    #             http://img.tvmao.com/images/logo/channel/AHTV1/AHTV1_140x140.png
    #             ]]>
    #         </logo>
    #         <name>
    #             <![CDATA[ 安徽卫视 ]]>
    #         </name>
    #     </channel>
    # </document>"""
    params = {
        'secret': SECRET_KEY,
    }
    url = '%s/%s?%s' % (THIRD_PARTY_EPG_URL_BASE, 'channel', urlencode(params))
    try:
        web_page = urlopen(url, timeout=5).read()
    except Exception as e:
        logging.error('Fetch channel xml failed. %s' % url)
        logging.exception(e)
        return None
    return web_page


@retry(Exception, tries=5, delay=1, backoff=2)
def fetch_update_xml(next_time):
#     return """
# <document>
# <schedules>
# <schedule channel_id="CCTV1" epg_code="CCTV1" date="">
# <event id="819390800" op="del"/>
# </schedule>
# <schedule channel_id="CCTV1" epg_code="CCTV1" date="2017-12-07">
# <event id="819448190" op="add">
# <start_time>18:30</start_time>
# <end_time>18:58</end_time>
# <title>
# <![CDATA[ 安徽新闻联播 ]]>
# </title>
# </event>
# </schedule>
# </schedules>
# </document>
# """
    params = {
        'secret': SECRET_KEY,
        'time': next_time
    }
    url = '%s/%s?%s' % (THIRD_PARTY_EPG_URL_BASE, 'update', urlencode(params))
    try:
        web_page = urlopen(url, timeout=5).read()
    except Exception as e:
        logging.error('Fetch update xml failed. %s' % url)
        logging.exception(e)
        return None
    return web_page


def channel_loop():
    global channel_cache
    channel_cache = fetch_channel_xml()
    channel_timer = threading.Timer(12 * 60 * 60, channel_loop)
    channel_timer.setDaemon(True)
    channel_timer.start()


def schedule_loop():
    global schedule_cache_dict, cur_time
    if channel_cache is not None:
        try:
            with acquire_timeout(mutex, 3) as acquired:
                if acquired:
                    channel_root = et.fromstring(channel_cache)
                    cur_time = time.strftime('%Y%m%d%H%M%S', time.localtime())
                    for index,channel in enumerate(channel_root.iter('channel')):
                        id = channel.get('id')
                        name = channel.find('name')
                        schedule_xml = fetch_schedule_xml(id)
                        if schedule_xml is not None:
                            schedule_cache_dict[id] = schedule_xml
                else:
                    raise Exception('Failed to get mutex!')
                # sleep(.1)
        except Exception as e:
            logging.exception(e)
            time.sleep(1)
            logging.error('parse channel_cache xml failed. Try again after 1 second')
            schedule_loop()
        else:
            t = threading.Timer(12*60*60, schedule_loop)
            t.setDaemon(True)
            t.start()


@lock_decorator
def update_xml_process(update_xml: et.Element):
    if update_xml.find('schedules') is None:return
    for schedule in update_xml.find('schedules').iter('schedule'):
        channel_id = schedule.get('channel_id')
        date = schedule.get('date')
        epg_code = schedule.get('epg_code')
        old_schedule = schedule_cache_dict.get(channel_id)
        try:
            old_schedule = et.fromstring(old_schedule)
        except Exception as e:
            logging.exception(e)
            return None
        for event in schedule.iter('event'):
            op = event.get('op')
            event_id = event.get('id')
            if op == 'add':
                child_schedule = old_schedule.find(".//schedule[@date='%s']"%date)
                if child_schedule is None:
                    child_schedule = et.SubElement(old_schedule,
                                  'schedule',
                                  attrib={'channel_id':channel_id,'epg_code':epg_code,'date':date}
                    )
                item = child_schedule.find(".//event[@id='%s']"%event_id)
                if item is not None:
                    child_schedule.remove(item)
                event.attrib.pop('op')
                child_schedule.append(event)
            elif op == 'del':
                item = old_schedule.find(".//event[@id='%s']"%event_id)
                if item is None:continue
                old_schedule.find(".//event[@id='%s']/.."%event_id).remove(item)
        schedule_cache_dict[channel_id] = et.tostring(old_schedule)


def update_loop():
    global cur_time
    logging.debug('Enter update loop')
    update_xml = fetch_update_xml(cur_time)
    try:
        while update_xml is not None:
            update_root = et.fromstring(update_xml)
            update_xml_process(update_root)
            next_time = update_root.find('next_time')
            if next_time is None:
                update_xml = None
            else:
                cur_time = next_time.text
                update_xml = fetch_update_xml(cur_time)
    except Exception as e:
        logging.exception(e)
    finally:
        t = threading.Timer(10,update_loop)
        t.setDaemon(True)
        t.start()


def fetch_all_data():
    channel_loop()
    schedule_loop()
    update_loop()


if __name__ == '__main__':
    fetch_all_data()
    # t = threading.Thread(target=refresh_caches)
    # t.setDaemon(True) # Kill the thread t when the main process stopped.
    # t.start()
    logging.info('start running flask')
    app.run(host='0.0.0.0', port=int(PORT), debug=False)
    logging.info('EPG Master Server Stopped!')


"""
<document>
<next_time>20171207215208</next_time>
<schedules>
<schedule channel_id="AHTV1" epg_code="AHTV1" date="">
<event id="812007150" op="del"/>
</schedule>
<schedule channel_id="AHTV1" epg_code="AHTV1" date="2017-12-07">
<event id="819448190" op="add">
<start_time>18:30</start_time>
<end_time>18:58</end_time>
<title>
<![CDATA[ 安徽新闻联播 ]]>
</title>
</event>
</schedule>
<schedule channel_id="AHTV1" epg_code="AHTV1" date="">
<event id="812007155" op="del"/>
</schedule>
</schedules>
</document>
"""