from flask import (
    Flask,
    request,
    make_response
)
from flask_caching import Cache
from flask_cors import CORS
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

if getattr(sys, 'frozen', False):
    cur_path = os.path.dirname(sys.executable)
elif __file__:
    cur_path = os.path.dirname(os.path.realpath(__file__))
log_file_name = str(Path(cur_path) / 'log' / 'epg.log')
log_file_handler = RotatingFileHandler(
    filename=log_file_name, maxBytes=10*1024*1024, backupCount=3)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s %(message)s',
                    handlers=[log_file_handler]
                    )
logging.info('log file created')

MASTER_PATH = "http://api.deepepg.com/api"
PORT = 10009
SECRET_KEY = 'VYDcCe1s'

app = Flask('__name__')
CORS(app)
cache = Cache()
cache.init_app(app, config={
    "CACHE_TYPE": "simple",
    "CACHE_DEFAULT_TIMEOUT": 600, })


@app.route('/EPG/channel', methods=['GET'])
@cache.cached(timeout=3600)
def channel():
    web_page = ""
    params = {
        'secret': SECRET_KEY,
    }
    url = '%s/%s?%s' % (MASTER_PATH, 'channel', urlencode(params))
    try:
        web_page = urlopen(url, timeout=20).read()
    except Exception as e:
        logging.error('Fetch channel xml failed. %s' % url)
        logging.exception(e)
        # raise Exception('Error fetch channel xml')
    rsp = make_response(web_page)
    rsp.mimetype = 'text/xml'
    return rsp


@app.route("/EPG/schedule/<channelName>", methods=["GET"])
@cache.cached()
def program(channelName):
    web_page = ""
    params = {
        'secret': SECRET_KEY,
        'id': channelName
    }
    url = '%s/%s?%s' % (MASTER_PATH, 'schedule', urlencode(params))
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
