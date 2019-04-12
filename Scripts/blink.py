'''
    File name: blink.py
    This code is based on Dullage's code: https://github.com/Dullage/Home-AssistantConfig/blob/master/python_scripts/blink.py
    Date last modified: @ 04/12/2019 9:55 AM
    Python Version: 3.7

    This script downloads the lastest video clip from blink server for a specified camera (by name), without region issues.  
    
    Usage: python blink.py [filename]
            e.g: 
                - python blink.py
                - python blink.py FrontDoor_2019_04_08_17_43.mp4

    * a) configure the User Variables: videoSavePath, secretsFileLocation, cameraName
      b) configure required secret parameters 
      c) filename defaults to BlinkVideo.mp4, if the script is ran without the filename arg 

    How I am using it with nodered: 
        1. Define a shell command in HA
            blink: python3 /config/blink/blink.py {{videoFilename}}
        2. in NodeRed: Door Open --> Delay 30 secs --> Use moment to generate a filename with the current timestamp --> call the shell command with the filename 
                       --> send the video via telegram 
    
'''

from requests import get, post
from json import dumps as json_dumps
from datetime import datetime
from dateutil.relativedelta import relativedelta
from time import sleep
from yaml import load as yaml_load, YAMLError
import sys
from os import system
import logging

########### USER VARIABLES ###########

videoSavePath = "/config/www"
secretsFileLocation = "/config"
cameraName = "Front Door"

goBackMinutes = 3 # Videos created before this many minutes ago will be ignored
waitTimeoutSeconds = 60 # How long to wait for a video before giving up

"""
This script also relises on the following entries in the secrets.yaml file.

blinkHassApiBaseURL - e.g. "https://www.myhass.com:8123"
blinkHassApiToken - a Home Assistant long live access token.
blinkUsername - Your Blink username
blinkPassword - Your blink password
"""

######################################

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

## assign the video filename from arg
if (len(sys.argv) == 2):
    videoFilename = sys.argv[1]
else:
    videoFilename = "BlinkVideo.mp4"
logging.debug(f"provided filename: {videoFilename}")

# Load secrets
with open("{0}/secrets.yaml".format(secretsFileLocation), "r") as secretsFile:
    try:
        secret = yaml_load(secretsFile)
    except YAMLError as exc:
        print(exc)

# Get an authentication token from Blink
endpoint = "https://rest-prod.immedia-semi.com/login"

headers = {
    "Host": "prod.immedia-semi.com",
    "Content-Type": "application/json"
}

data = {
    "email": secret["blinkUsername"],
    "password": secret["blinkPassword"],
    "client_specifier": "iPhone 9.2 | 2.2 | 222"
}

res = post(endpoint, headers=headers, data=json_dumps(data))
region = res.json()["region"]
logging.debug(f"region retrieved: {region}")

region = list(region.keys())[0]

response = post(endpoint, headers=headers, data=json_dumps(data))
token = response.json()["authtoken"]["authtoken"]

logging.debug(f"Token: {token}")

# We need to grab the last video but only if it was created recently (goBackMinutes) as the camera may not have finished yet. Grab the current time help with this.
start = datetime.today()
since = (start - relativedelta(minutes=goBackMinutes)).strftime("%Y-%m-%dT%H:%M:%S+00:00")

# Keep refreshing the video list until we have a video from the last minute.
while True:

    # Get a list of videos, assume page 0 has the most recent. Convert the JSON response to a dict.
    responseData = get(
        #"https://rest-prde.immedia-semi.com/api/v2/videos/changed?since={0}&page=1".format(since),
        "https://rest-"+region+".immedia-semi.com/api/v2/videos/changed?since={0}&page=1".format(since),
        headers={"Host": "rest-prde.immedia-semi.com", "TOKEN-AUTH": token}
    ).json()

    videos = responseData["videos"]

    latestVideoUrl = None
    if len(videos) >= 1:
        latestVideoUrl = videos[0]["address"]
        for i in range(len(videos)):
            camName = videos[i]["camera_name"]
            # print(i, videos[i]["camera_name"])
            if (camName == cameraName):
                latestVideoUrl = videos[i]["address"]
                logging.debug(f'Found a video for camera {cameraName}')

                break
        break
    else:
        if datetime.today() > (start + relativedelta(seconds=waitTimeoutSeconds)):
            latestVideoUrl = None
            elapsedTime = "N/A"
            break
        else:
            # Loop. Wait a second so that we"re not spamming the API too quickly.
            sleep(1)

# If we have a video send it.
if latestVideoUrl is not None:
    # Download the video.
    response = get(
        "https://rest-"+region+".immedia-semi.com{0}".format(latestVideoUrl),
        headers={"Host": "prod.immedia-semi.com", "TOKEN_AUTH": token}
    )

    # Save it to disk.
    videoFullPath = f"{videoSavePath}/{videoFilename}"
    f = open(videoFullPath, "wb")
    f.write(response.content)
    f.close()
    
    logging.debug(f"File saved: {videoFullPath}")
