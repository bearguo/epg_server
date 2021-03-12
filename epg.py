import configparser
import html
import threading
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
import datetime
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
import os
import sys
from xml.etree import ElementTree as et
from retry import retry
import time

if getattr(sys, 'frozen', False):
    cur_path = os.path.dirname(sys.executable)
elif __file__:
    cur_path = os.path.dirname(os.path.realpath(__file__))
log_file_name = str(Path(cur_path) / 'conf' / 'epg.log')
#log_file_handler = TimedRotatingFileHandler(filename=log_file_name, when="D", interval=1, backupCount=3)
log_file_handler = RotatingFileHandler(
    filename=log_file_name, maxBytes=10*1024*1024, backupCount=3)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s %(message)s',
                    handlers=[log_file_handler]
                    )
logging.info('log file created!')
PORT = 10010
try:
    cf = configparser.ConfigParser()
    cf.read(str(Path(cur_path) / 'conf' / 'epg.conf'))
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
    # logging.info("in get schedule xml function!", debug_counter)
    web_page = urlopen(url, timeout=5).read()
    return web_page


@wrapcache.wrapcache(timeout=12 * 60 * 60)
def get_channel_xml(url: str):
    # global debug_counter
    # debug_counter += 1
    # logging.info("in get channel xml function!", debug_counter)
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
        try:
            global schedule_cache_dict
            wrapcache.flush()
            schedule_cache_dict = {}
        except:
            logging.warning('refresh caches failed')
            time.sleep(10)
        else:
            logging.info('refresh caches success')
            time.sleep(24 * 60 * 60)


@contextmanager
def acquire_timeout(lock, timeout):
    result = lock.acquire(timeout=timeout)
    yield result
    if result:
        try:
            lock.release()


def cache_lock(func):
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
    logging.info('Enter channel:%s' % channel_id)
    params = {
        'secret': SECRET_KEY,
        'id': channel_id
    }
    url = '%s/%s?%s' % (THIRD_PARTY_EPG_URL_BASE,
                        'schedule', urlencode(params))
    try:
        web_page = urlopen(url, timeout=20).read()
    except Exception as e:
        logging.error('Fetch schedule xml failed. %s' % url)
        logging.exception(e)
        raise Exception('Error fetching schedule url')
        return None
    return web_page


@retry(Exception, delay=1, backoff=2)
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
    logging.info('Enter fetch channel')
    params = {
        'secret': SECRET_KEY,
    }
    url = '%s/%s?%s' % (THIRD_PARTY_EPG_URL_BASE, 'channel', urlencode(params))
    try:
        web_page = urlopen(url, timeout=20).read()
    except Exception as e:
        logging.error('Fetch channel xml failed. %s' % url)
        logging.exception(e)
        raise Exception('Error fetch channel xml')
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
        web_page = urlopen(url, timeout=20).read()
    except Exception as e:
        logging.error('Fetch update xml failed. %s' % url)
        logging.exception(e)
        raise Exception('Error fetch update xml')
    return web_page


def channel_loop():
    global channel_cache
    try:
        channel_cache = fetch_channel_xml()
    except Exception as e:
        logging.exception(e)
        logging.info('fetch channel xml failed. Retry after 10 seconds')
        channel_timer = threading.Timer(10, channel_loop)
        channel_timer.setDaemon(True)
        channel_timer.start()
    else:
        logging.info('fetch channel success')
        channel_timer = threading.Timer(12 * 60 * 60, channel_loop)
        channel_timer.setDaemon(True)
        channel_timer.start()


def end_time_with_0(program_list):
    return program_list.find('end_time').text == '00:00'


def filter_cross_midnight_program(schedule_xml):
    """将跨午夜相同节目被差分成两个节目的部分合并为一个节目"""
    schedule_xml = et.fromstring(schedule_xml)

    # 1. 找出所有结束时间为00:00的节目，记录其所属日期
    parent_map = dict((c, p) for p in schedule_xml.getiterator() for c in p)
    cross_program = schedule_xml.findall(".//event")
    cross_program_night = filter(end_time_with_0, cross_program)

    # 2. 判断是否在该节目的第二天存在起始时间为00:00且节目名称相同的节目
    cross_program_clean = []
    for program in cross_program_night:
        try:
            program_date = parent_map[program].get('date')
            program_date = datetime.datetime.strptime(program_date, '%Y-%m-%d')
            next_date = program_date + datetime.timedelta(days=1)
            next_date = next_date.strftime('%Y-%m-%d')
            next_day_programs = schedule_xml.find(
                ".//schedule[@date='%s']" % next_date).iter('event')
            next_day_programs = [next_program for next_program in next_day_programs if (
                next_program.find('start_time').text == '00:00'
                and next_program.find('title').text == program.find('title').text
            )]
            # 3. 修改该结束时间为00:00的节目的结束时间为第二天节目的结束时间,删除第二天的该节目
            if next_day_programs:
                program.find('end_time').text = next_day_programs[0].find(
                    'end_time').text
                parent_map[next_day_programs[0]].remove(next_day_programs[0])
        except:
            continue
    # 4. 将element tree转化为字符串返回
    return et.tostring(schedule_xml)


def schedule_loop():
    global schedule_cache_dict, cur_time
    logging.info('start schedule_loop')
    if channel_cache is not None:
        with acquire_timeout(mutex, 3) as acquired:
            try:
                if acquired:
                    channel_root = et.fromstring(channel_cache)
                    cur_time = time.strftime('%Y%m%d%H%M%S', time.localtime())
                    for index, channel in enumerate(channel_root.iter('channel')):
                        id = channel.get('id')
                        name = channel.find('name')
                        schedule_xml = fetch_schedule_xml(id)
                        try:
                            schedule_xml_clean = filter_cross_midnight_program(
                                schedule_xml)
                        except Exception as e:
                            logging.exception(e)
                            schedule_xml_clean = schedule_xml
                        if schedule_xml_clean is not None:
                            logging.info('fetch %s shcedule success' % id)
                            schedule_cache_dict[id] = schedule_xml_clean
                else:
                    raise Exception('Failed to get mutex!')
                time.sleep(.1)
            except Exception as e:
                mutex.release()
                logging.exception(e)
                logging.error(
                    'parse channel_cache xml failed. Try again after 30 second')
                t = threading.Timer(30, schedule_loop)
                t.setDaemon(True)
                t.start()
            else:
                t = threading.Timer(1 * 60 * 60, schedule_loop)
                t.setDaemon(True)
                t.start()


@cache_lock
def update_xml_process(update_xml: et.Element):
    if update_xml.find('schedules') is None:
        return
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
                child_schedule = old_schedule.find(
                    ".//schedule[@date='%s']" % date)
                if child_schedule is None:
                    child_schedule = et.SubElement(old_schedule,
                                                   'schedule',
                                                   attrib={
                                                       'channel_id': channel_id, 'epg_code': epg_code, 'date': date}
                                                   )
                item = child_schedule.find(".//event[@id='%s']" % event_id)
                if item is not None:
                    child_schedule.remove(item)
                event.attrib.pop('op')
                try:
                    modified_event_time = event.find('start_time').text
                except Exception as e:
                    logging.error("can not get start time of modified event")
                    logging.error(e)
                    modified_event_time = '00:00'
                # child_schedule.append(event)
                cnt = 0
                for old_event in child_schedule.iter('event'):
                    try:
                        if old_event.find('start_time').text < modified_event_time:
                            cnt += 1
                        else:
                            break
                    except Exception as e:
                        logging.error(
                            'schedule xml format error. can not get start time of program %s' % event.attrib)
                        logging.error(e)
                        break
                child_schedule.insert(cnt, event)
            elif op == 'del':
                item = old_schedule.find(".//event[@id='%s']" % event_id)
                if item is None:
                    continue
                old_schedule.find(
                    ".//event[@id='%s']/.." % event_id).remove(item)
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
        t = threading.Timer(5 * 60, update_loop)
        t.setDaemon(True)
        t.start()


def fetch_all_data():
    channel_loop()
    schedule_loop()
    update_loop()


if __name__ == '__main__':
    fetch_all_data()
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
