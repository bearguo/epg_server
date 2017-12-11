# EPG Server (Python3)
This is the epg server which is the upgraded version of previous epg-slave-master project. 
# Usage
1. Run the epg\_slave.py with python **and** followed by a parameter \<port\> number.
```shell
python epg_slave.py 9999
```

2. Run `pyinstaller -F epg.py` to build a excutable program in `dist\epg` then run: `./dist/epg`

# Configuration
configuration file is 'epg.conf' in the same folder with epg_sla

Next is the configuration file content:
```shell
[server]
port=10010 # Specify server's tcp port

[epg_master]
base_url = http://1.8.203.198:9999/EPG # This line specified the master epg server base url.
```

# API 
1. Get channels xml
`http://\<ip\>:\<port\>/EPG/channel?secret=VYDcCe1s`

Examples:
```shell
http://localhost:10011/EPG/channel?secret=VYDcCe1s
```

2. Get program information for one channel
`http://\<ip\>:\<port\>/EPG/schedule?secret=VYDcCe1s&id=\<channel_id\>`

Examples:
```shell
http://localhost:10011/EPG/schedule?secret=VYDcCe1s&id=CCTV1
```


