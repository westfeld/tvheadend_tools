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

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from typing import Optional
import requests

# Configuration

TVHEADEND_SERVER_URL = "http://localhost/tv"
TVHEADEND_SERVER_USER = None
TVHEADEND_SERVER_PASSWD = None

class CommercialDetector:
    """
    class that encapsulates commercial detection using comskip
    """
    def __init__(self, config:Optional[str]=None):
        self.config = config
        self.chapterfile:str = ""
        self.raw_detection_result:List[str] = []
        self.ffmetadata = ""

    def detect_commercials(self, video_filename:str):
        """
        starts detection of commercials using comskip
        """

        commercial_file = os.path.splitext(os.path.basename(video_filename))[0]+'.txt'
        temp_dir = tempfile.TemporaryDirectory()
        commercial_file_path = os.path.join(temp_dir.name, commercial_file)

        # build comskip command
        comskip_call = ['comskip']
        if self.config:
            comskip_call.extend(['--ini='+ self.config])
        comskip_call.append(video_filename)
        comskip_call.append(temp_dir.name)

        try:
            subprocess.run(comskip_call, check=True).stdout
        except subprocess.CalledProcessError as err:
            raise TranscodeError() from err
        with open(commercial_file_path, encoding="latin1") as fptr:
            self.raw_detection_result = fptr.readlines()

    def generate_metadata(self):
        """
        write commercials als ffmpeg compatible chapter file
        """

        commercials = []
        content = []
        if len(self.raw_detection_result) < 3:
            return
        header_regexp = r"FILE PROCESSING COMPLETE\s+(\d+) FRAMES AT\s+(\d+)"
        header_match = re.match(header_regexp, self.raw_detection_result[0])
        if header_match:
            last_frame = int(header_match.group(1))
            frame_rate = header_match.group(2)
        else:
            print ("invalid commercials file")
            return
        chapter_regexp = r"(\d+)\s+(\d+)"

        for i in range(2, len(self.raw_detection_result)):
            chapter_match = re.match(chapter_regexp, self.raw_detection_result[i])
            if not chapter_match:
                continue
            (start, end) = chapter_match.group(1, 2)
            if (int(end) - int(start)) > 10:
                commercials.append((start, end))

        last_pos = 1
        cont_idx = 0
        for cont_idx in range(0, len(commercials)):
            com = commercials[cont_idx]
            if int(com[0]) > last_pos:
                content.append((last_pos, com[0]))
            last_pos = int(com[1])
            if cont_idx == (len(commercials)-1) and last_pos < last_frame:
                content.append((last_pos, last_frame))

        self.ffmetadata += self._chapter_as_string(frame_rate, "content", content)
        self.ffmetadata += self._chapter_as_string(frame_rate, "commercial",
                                                   commercials)

    def _chapter_as_string(self, frame_rate:int, label:str, segments) -> str:
        """
        generate string representation of a list of segments
        """
        idx = 0
        chapter_list = ""
        for seg in segments:
            idx += 1
            chapter_list += f"""[CHAPTER]
TIMEBASE=100/{frame_rate}
START={seg[0]}
END={seg[1]}
title={label} {idx}
"""
        return chapter_list


class TVHRecordParameter:
    """
    class that represents a record parameter
    """
    def __init__(self, param_dict:dict):
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
    def __init__(self, uuid:str, server_base_url:str, user:Optional[str]=None,
                 passwd:Optional[str]=None):
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

    def __init__(self, uuid:str, server_base_url:str, user:Optional[str]=None,
                 passwd:Optional[str]=None):
        super().__init__(uuid, server_base_url, user, passwd)
        channel_record = TVHRecord(self.channel.value, self.server_base_url,
                                  self.user, self.passwd)
        self.disp_channel = channel_record.name
        self.metadata_file:str = ""
        self.transcoded_path:str = ""
        self.temp_dir:tempfile.TemporaryDirectory = None
        self.ffmetadata = ""
        self.generate_metadata()

    def generate_metadata(self):
        """
        writes ffmpeg compatible metadatafile
        """
        start_time = time.localtime(self.start.value)
        start_time_formatted = time.strftime("%Y-%m-%d", start_time)
        self.ffmetadata = f''';FFMETADATA1
title={self.disp_title.value}
artist={self.disp_subtitle.value}
description={self.disp_description.value}
date={start_time_formatted}
network={self.disp_channel}'''

    def detect_commercials(self, configfile=""):
        """
        starts the detection of commercials in video file
        and appends chapter marks for commercials
        """
        com = CommercialDetector(config=configfile)
        com.detect_commercials(self.filename.value)
        com.generate_metadata()
        self.ffmetadata += "\n" + com.ffmetadata

    def start_transcoding(self, temp_dir:Optional[str]=None, factor:float=0.6):
        """
        starts the transcoding with ffmpeg
        """

        self.temp_dir = tempfile.TemporaryDirectory(dir=temp_dir)
        self.metadata_file = os.path.join(self.temp_dir.name, "metadata.txt")
        transcoded_file = os.path.splitext(os.path.basename(self.filename.value))[0]+'.mp4'
        # temp outputfile for transcoding
        temp_out_file = os.path.join(self.temp_dir.name, transcoded_file)
        self.transcoded_path = os.path.join(os.path.dirname(self.filename.value), transcoded_file)

        with open(self.metadata_file, "w", encoding="utf-8") as fptr:
            fptr.write(self.ffmetadata)

        target_video_bitrate = self._calculate_target_video_bitrate(factor=factor)

        ffmpeg_call = ['ffmpeg', '-hide_banner', '-i', self.filename.value, '-i',
                       self.metadata_file, '-vsync', 'cfr',
                       '-c:v', 'h264_v4l2m2m', '-b:v',
                       str(target_video_bitrate),
                       '-pix_fmt', 'yuv420p', '-level', '4',
                       '-c:a', 'aac', '-b:a', '128k', '-ac', '2',
                       '-map_metadata', '1', '-vf', 'yadif', '-y',
                       temp_out_file]
        try:
            subprocess.run(ffmpeg_call, check=True)
        except subprocess.CalledProcessError as err:
            raise TranscodeError() from err
        # move transcoded file to final destination
        shutil.move(temp_out_file, self.transcoded_path)
        # update file location in TVHeadend and delete old file
        if self.update_file_location():
            os.remove(self.filename.value)

    def _calculate_target_video_bitrate(self, factor:float) -> int:
        """
        Internal method to calculate the target bitrate based on the source
        bitrate multiplied by a compression factor.
        factor=0.6 means target bitrate = factor*source bitrate
        """

        ffprobe_call = ['ffprobe', '-print_format', 'json' , '-show_format',
                        '-select_streams', 'v', self.filename.value ]
        try:
            raw = subprocess.run(ffprobe_call, check=True, capture_output=True).stdout
        except subprocess.CalledProcessError as err:
            raise TranscodeError() from err
        stream_props = json.loads(raw)
        src_video_bitrate = int(stream_props['format']['bit_rate'])
        # calculate target bitrate, rounded to next 1024 multiple
        return int((src_video_bitrate * factor) // 1024 * 1024)

    def _source_video_frame_rate(self) -> float:
        """
        Gets the frame rate of the source video
        """

        ffprobe_call = ['ffprobe', '-print_format', 'json' , '-show_streams',
                        '-select_streams', 'v', self.filename.value ]
        try:
            raw = subprocess.run(ffprobe_call, check=True, capture_output=True).stdout
        except subprocess.CalledProcessError as err:
            raise TranscodeError() from err
        stream_props = json.loads(raw)
        avg_video_framerate_string = stream_props['streams'][0]['avg_frame_rate']
        (nom, denom) = avg_video_framerate_string.split("/")
        return float(nom)/float(denom)

    def update_file_location(self) -> bool:
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
    * use comskip to detect commercials in recording
    * generate metadata file
    * determine target bitrate from source bitrate
    * start ffmpeg transcoding
    * move file in place via API
    * delete transport stream file
    """

    if len(sys.argv) != 4:
        print("use uid of DVR record as first and and the status as the second "
              "argument, an optional fourth argument with the config file for "
              "comskip can be provided")
        return
    record_uuid = sys.argv[1]
    status = sys.argv[2]
    if len(sys.argv) == 4:
        comskip_configfile = sys.argv[3]
    else:
        comskip_configfile=""
    # check if recording was successful
    if status != "OK":
        return
    record = TVHDVRRecord(record_uuid, TVHEADEND_SERVER_URL,
                          TVHEADEND_SERVER_USER,
                          TVHEADEND_SERVER_PASSWD)
    try:
        record.detect_commercials(configfile=comskip_configfile)
        record.start_transcoding()
    except Exception as err :
        print(err)

if __name__ == "__main__":
    main()
