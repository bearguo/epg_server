from flask import (
    Flask,
    request,
    make_response
)
from flask_cors import CORS
import os, sys, logging
from logging.handlers import RotatingFileHandler
import configparser
from pathlib import Path
from urllib.parse import urljoin, urlencode, urlparse
from urllib.request import urlopen

if getattr(sys, 'frozen', False):
    cur_path = os.path.dirname(sys.executable)
elif __file__:
    cur_path = os.path.dirname(os.path.realpath(__file__))
log_file_name = str(Path(cur_path) / 'conf' / 'epg.log')
log_file_handler = RotatingFileHandler(filename=log_file_name, maxBytes=10*1024*1024, backupCount=3)
#log_file_handler = TimedRotatingFileHandler(filename=log_file_name, when="D", interval=1, backupCount=3)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s %(message)s',
                    handlers=[log_file_handler]
                    )
logging.info('log file created')
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

@app.route('/EPG/channel', methods=['GET'])
def channel():
    web_page = ''
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

    params = {
        'secret': SECRET_KEY,
    }
    url = '%s/%s?%s' % (THIRD_PARTY_EPG_URL_BASE, 'channel', urlencode(params))
    try:
        web_page = urlopen(url, timeout=20).read()
    except Exception as e:
        logging.error('Fetch channel xml failed. %s' % url)
        logging.exception(e)
        # raise Exception('Error fetch channel xml')
    rsp = make_response(web_page)
    rsp.mimetype = 'text/xml'
    return rsp

@app.route('/EPG/schedule')
def schedule():
    web_page = ''
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

    logging.info('Enter channel:%s' % channel_id)
    params = {
        'secret': SECRET_KEY,
        'id': channel_id
    }
    url = '%s/%s?%s' % (THIRD_PARTY_EPG_URL_BASE, 'schedule', urlencode(params))
    try:
        web_page = urlopen(url, timeout=20).read()
    except Exception as e:
        logging.error('Fetch schedule xml failed. %s' % url)
        logging.exception(e)
        # raise Exception('Error fetching schedule url')
    rsp = make_response(web_page)
    rsp.mimetype = 'text/xml'
    return rsp


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(PORT), debug=False)