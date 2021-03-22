from unittest import TestCase
from typing import Iterator

from aiortc.avmedia.mediastreams import AvMediaStreamProducer, AvVideoStreamTrack
from aiortc.rtcrtpparameters import RTCRtpCodecParameters

from av.packet import Packet

class StreamProducerTest(TestCase):

    class EmptyTrack(AvVideoStreamTrack):
        async def to_stream(self, force_keyframe, time_origin, codec: RTCRtpCodecParameters) -> Iterator[Packet]:
            return


    def test_not_started(self):
        producer = AvMediaStreamProducer(StreamProducerTest.EmptyTrack())
        with self.assertRaises(StopIteration):
            next(producer.toStream(False, 0, None))


    def test_started_empty(self):
        producer = AvMediaStreamProducer(StreamProducerTest.EmptyTrack())
        producer.start()
        with self.assertRaises(StopIteration):
            next(producer.toStream(False, 0, None))

