import fractions
import threading
import asyncio
from pyee import AsyncIOEventEmitter

from abc import abstractmethod
from typing import Optional, Iterator

from av import AVError
from av.frame import Frame
from av.packet import Packet

from aiortc.utils import uint32_add
from aiortc.mediastreams import MediaStreamTrack
from aiortc.rtcrtpparameters import RTCRtpCodecParameters


AUDIO_PTIME = 0.020  # 20ms audio packetization
VIDEO_CLOCK_RATE = 90000
VIDEO_PTIME = 1 / 30  # 30fps
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)


def convert_timebase(
    pts: int, from_base: fractions.Fraction, to_base: fractions.Fraction
) -> int:
    if from_base != to_base:
        pts = int(pts * from_base / to_base)
    return pts


class AvMediaStreamTrack(MediaStreamTrack):
    """
    A single media track within a stream.
    """

    kind = "unknown"

    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    async def to_stream(self, force_keyframe, time_origin, codec: RTCRtpCodecParameters) -> Iterator[Packet]:
        """
        Working with PyAV packets opens up more possibilities to use libav pipelines
        which is especially useful to support hardware supported parts of a pipeline.
        Additionally, it saves some type conversations in processing.
        """
        pass

    async def recv(self) -> Frame:
        """
        Old abstract interface invalidated. Proof of concept only.
        TODO: For a clean merge, this should get some refactoring on main
        """
        pass


class AvAudioStreamTrack(AvMediaStreamTrack):
    """
    Baseclass for audio av stream implementations
    """
    kind = "audio"

    def elapsed_time(self, time_origin, time_base, pts):
        pass

class AvVideoStreamTrack(AvMediaStreamTrack):
    """
    Baseclass for Video av stream implementations
    """
    kind = "video"

    def elapsed_time(self, time_origin, time_base, pts):
        '''
        Elapsed time is implemented as a kind of "global timebase clock" to synchronize
        audio and video (grabbed) live streams
        '''
        return uint32_add(time_origin, convert_timebase(pts, time_base, VIDEO_TIME_BASE))


class AvMediaStreamProducer(AvMediaStreamTrack):
    '''
    Decorator for media streams to consume packets in parallel running streams.
    The packets are queues in an inter-thread queue.
    '''
    def __init__(self, decorated_track: AvMediaStreamTrack, bufsize=200):
        self.__decorated_track = decorated_track
        self.__queue = asyncio.Queue(maxsize=bufsize, loop=asyncio.get_event_loop())
        self.__thread_quit: Optional[threading.Event] = threading.Event()
        self.__thread: Optional[threading.Thread] = threading.Thread(
                name="StreamProducer:" + self.__decorated_track.__class__.__name__,
                target=AVMediaStreamProducer._produce_packets,
                args=(
                    self.__thread_quit,
                    self.__queue,
                    self.__decorated,
                ),
            )


    @staticmethod
    async def _produce_packets(quit_event, queue, decorated_track: AvMediaStreamTrack):
        while not quit_event.is_set():
            try:
                for paket in decorated_track.to_stream():
                    await queue.put(paket)
                await queue.put(None)
            except (AVError, StopIteration):
                # use None packets as marker to separate packets
                # consued together
                await queue.put(None)


    async def start(self):
        """
        Start prducing packets/grabbing.
        """
        self.__thread.start()


    async def stop(self):
        """
        Stop grabbing/packet production.
        """
        if self.__thread is not None:
            self.__thread_quit.set()
            self.__thread.join()
            self.__thread = None


    async def __del__(self):
        """
        Make sure running producers are stopped on delete.
        """
        await self.stop()


    async def to_stream(self, force_keyframe, time_origin, codec: RTCRtpCodecParameters) -> Iterator[Packet]:
        return iter(self.__queue.get() , None)



