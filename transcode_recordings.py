#!/usr/bin/env python3
"""
Script for postprocessing of TVheadend recordings
The MPEG-2 transport stream file will be transcoded in H.264 mp4 file
and the EPG metadata is embedded

Uses hardware encoding support in RPi 4

Usage: use this script in a TVHeadend DVR configuration as a post-processing
comamnd.

Invocation: transcode_recording.py %U %e
                                    ^  ^
                                    |  |
                                    |  -- Error code from recording, should be
                                    |     "OK"
                                    |
                                    ----- UUID of recording

"""

import os
import shutil
import subprocess
import sys
import tempfile
import time

import requests


# Configuration

TVHEADEND_SERVER_URL = "http://localhost/tv"
TVHEADEND_SERVER_USER = None
TVHEADEND_SERVER_PASSWD = None


class TVHRecordParameter:
    """
    class that represents a record parameter
    """
    def __init__(self, param_dict):
        self.value = None
        for key, value in param_dict.items():
            if key == 'id':
                continue
            if type(value) in (str, int, float):
                setattr(self, key, value)

    def __repr__(self):
        if self.value:
            return self.value
        return ""


class TVHRecord:
    """
    class that represents a tvheadend record
    """
    def __init__(self, uuid, server_base_url, user=None, passwd=None):
        """
        get element by uuid
        """
        ts_url = 'api/idnode/load'
        payload = {'uuid': uuid}
        self.user = user
        self.passwd = passwd
        if user:
            self.auth = (user, passwd)
        else:
            self.auth = None
        self.server_base_url = server_base_url
        ts_query = f'{self.server_base_url}/{ts_url}'
        import pdb; pdb.set_trace()
        ts_response = requests.get(ts_query, params=payload, timeout=30,
                                   auth=self.auth)
        if ts_response.status_code != 200:
            return
        self.record_dict = ts_response.json()['entries'][0]
        self.type = self.record_dict['class']
        self.parameters = []
        for param in self.record_dict['params']:
            self.parameters.append(param['id'])
            setattr(self, param['id'], TVHRecordParameter(param))

class TranscodeError(Exception):
    """
    class that encapsulates an FFMPEG error
    """

class TVHDVRRecord(TVHRecord):
    """
    class that represents a recording of the DVR
    """

    def __init__(self, uuid, server_base_url, user=None, passwd=None):
        super().__init__(uuid, server_base_url, user, passwd)
        channel_record = TVHRecord(self.channel.value, self.server_base_url,
                                  self.user, self.passwd)
        self.disp_channel = channel_record.name
        self.metadata_file = None
        self.transcoded_path = None

    def create_metadata_file(self, filename):
        """
        writes ffmpeg compatible metadatafile
        """
        start_time = time.localtime(self.start.value)
        start_time_formatted = time.strftime("%Y-%m-%d", start_time)
        metadata_file_content = f''';FFMETADATA1
title={self.disp_title.value}
artist={self.disp_subtitle.value}
description={self.disp_description.value}
date={start_time_formatted}
network={self.disp_channel}'''

        with open(filename,"w", encoding='utf-8') as fptr:
            fptr.write(metadata_file_content)

    def start_transcoding(self, temp_dir:str=None):
        """
        starts the transcoding with ffmpeg
        """

        self.temp_dir = tempfile.TemporaryDirectory(dir=temp_dir)
        self.metadata_file = os.path.join(self.temp_dir.name, "metadata.txt")
        transcoded_file = os.path.splitext(os.path.basename(self.filename.value))[0]+'.mp4'
        # temp outputfile for transcoding
        temp_out_file = os.path.join(self.temp_dir.name, transcoded_file)
        self.transcoded_path = os.path.join(os.path.dirname(self.filename.value), transcoded_file)
        self.create_metadata_file(self.metadata_file)

        ffmpeg_call = ['ffmpeg', '-hide_banner', '-i', self.filename.value, '-i',
                       self.metadata_file, '-vsync', 'cfr',
                       '-c:v', 'h264_v4l2m2m', '-b:v', '1.8M',
                       '-pix_fmt', 'yuv420p', '-level', '4',
                       '-c:a', 'aac', '-b:a', '128k', '-ac', '2',
                       '-map_metadata', '1', '-vf', 'yadif', '-y',
                       temp_out_file]
        try:
            subprocess.run(ffmpeg_call, check=True)
        except subprocess.CalledProcessError as process_error:
            raise TranscodeError() from process_error
        # move transcoded file to final destination
        shutil.move(temp_out_file, self.transcoded_path)
        # update file location in TVHeadend and delete old file
        if self.update_file_location():
            os.remove(self.filename.value)


    def update_file_location(self):
        """
        moves the file in the TVheadend database
        """
        ts_url = 'api/dvr/entry/filemoved'
        ts_query = f'{self.server_base_url}/{ts_url}'
        post_data = {'src': self.filename.value, 'dst': self.transcoded_path }
        if not os.path.exists(os.path.dirname(self.transcoded_path)):
            return False
        ts_response = requests.post(ts_query, data=post_data, timeout=30,
                                    auth=self.auth)
        if ts_response.status_code != 200:
            print('Error code %d\n%s' % (ts_response.status_code, ts_response.content, ))
            return False
        return True

def main():
    """
    * find timer which has been completed
    * make sure the error code ist OK
    * generate metadata file
    * start ffmpeg transcoding
    * move file in place via API
    * delete transport stream file
    """

    if len(sys.argv) != 3:
        print("use uid of DVR record as first and and the status as the second "
              "argument")
        return
    record_uuid = sys.argv[1]
    status = sys.argv[2]
    # check if recording was successful
    if status != "OK":
        return
    record = TVHDVRRecord(record_uuid, TVHEADEND_SERVER_URL,
                          TVHEADEND_SERVER_USER,
                          TVHEADEND_SERVER_PASSWD)
    try:
        record.start_transcoding()
    except:
        pass

main()
