#
# Media streams that exploit libva/pyav properties more extensive, esp. to
# exploit hardware encoding/decoding properties of a device like raspberry pi cams.  
#
# Tips: You can check video4linux4 properties of a webcam with 
# > v4l2-ctl --list-formats

from aiortc.avmedia.mediastreams import AvVideoStreamTrack
from aiortc.rtcrtpparameters import RTCRtpCodecParameters
from typing import Iterator


import av  
from av.packet import Packet
from av.bitstream import (BitStreamFilter, BitStreamFilterContext, 
                            UnknownFilterError, bitstream_filters_availible)


class V4l2InputTrack(AvVideoStreamTrack):
    '''
    List options with
    > ffmpeg -f v4l2 -list_formats all -i /dev/video0

    See parameter documentation:
    https://ffmpeg.org/ffmpeg-devices.html#video4linux2_002c-v4l2
    '''
    def __init__(self, file, format="v4l2", 
                    options={
                        "video_size": "1920x1080",
                        "input_format": "h264",
                        "framerate": 30,
                        "timestamps": "abs"
                    },
                    container_options=None, stream_options=None,
                    metadata_encoding='utf-8', metadata_errors='strict',
                    buffer_size=32768, timeout=None):
        self.__input = av.open(file, format, mode='r',
                                options=options, container_options=container_options, 
                                stream_options=stream_options, 
                                metadata_encoding=metadata_encoding, 
                                metadata_errors=metadata_errors, buffer_size=buffer_size, 
                                timeout=timeout)
        self.__h264annexbsf = BitStreamFilterContext('h264_mp4toannexb')
        self.__firstpts = None

    def elapsed_time(self, time_origin, time_base, pts):
        '''
        Grabbing stream packets my not start with zero, so normalize timestamp from first packet
        '''
        if self.__firstpts is None:
            self.__firstpts = pts
        return super.elapsed_time(time_origin, time_base, self.__firstpts - pts)


    async def to_stream(self, time_origin, force_keyframe, codec: RTCRtpCodecParameters) -> Iterator[Packet]:
        '''
        Hardware encoders already deliver (nearly) ready packages.
        In case of H.264 (which is the proof case for raspberry pi cam), the packet
        requires a small post processing ("bit-filtering"), 
        which is done as an additional case here.

        The force_keyframe mode has been ignored yet also.
        The whole av media integration needs refactoring later anyway.  
        '''
        for packet in self.__input.demux():
            # h264 hardware encoder does not need encoding step,
            # but may need some post-processing
            yield(self.__h264annexbsf(packet))
        # rebase/normalize the timestamps
        #for packet in delivered_packets:
        #    packet.pts = self.elapsed_time(time_origin, packet.time_base, packet.pts)

    def stop(self) -> None:
        super.stop()
        self.__input.close()

