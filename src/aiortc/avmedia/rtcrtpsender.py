import asyncio
import logging
import fractions
import random
import clock
import traceback

from aiortc.utils import random16, random32, uint16_add, uint32_add
from aiortc.rtcrtpsender import RTCRtpSender
from aiortc.rtcrtpparameters import RTCRtpCodecParameters
from aiortc.rtp import RtpPacket

from aiortc.mediastreams import MediaStreamError
from aiortc.avmedia.mediastreams import AVMediaStreamTrack


logger = logging.getLogger("avmedia.rtcrtpsender")

RTP_HISTORY_SIZE = 128
RTT_ALPHA = 0.85

class AVRTCRtpSender(RTCRtpSender):
    """
    The :class:`RTCRtpSender` interface provides the ability to control and
    obtain details about how a particular :class:`MediaStreamTrack` is encoded
    and sent to a remote peer.

    :param trackOrKind: Either a :class:`MediaStreamTrack` instance or a
                         media kind (`'audio'` or `'video'`).
    :param transport: An :class:`RTCDtlsTransport`.
    """

    def __init__(self, avtrack: AVMediaStreamTrack, transport) -> None:
        super().__init(avtrack, transport)  

    async def stop(self):
        super().stop()

    async def _run_rtp(self, codec: RTCRtpCodecParameters) -> None:
        self.__log_debug("- RTP started")

        sequence_number = random16()
        timestamp_origin = random32()
        try:
            while True:
                if not self.__track:
                    await asyncio.sleep(0.02)
                    continue

                force_keyframe = self.__force_keyframe
                self.__force_keyframe = False
                avpackets = await self.__track.to_rtpstream(timestamp_origin, force_keyframe, codec)

                for i, avpacket in enumerate(avpackets):
                    packet = RtpPacket(
                        payload_type=codec.payloadType,
                        sequence_number=sequence_number,
                        timestamp=avpacket.pts,
                    )
                    packet.ssrc = self._ssrc
                    packet.payload = bytes(avpacket)
                    packet.marker = (i == len(avpackets) - 1) and 1 or 0

                    # set header extensions
                    packet.extensions.abs_send_time = (
                        clock.current_ntp_time() >> 14
                    ) & 0x00FFFFFF
                    packet.extensions.mid = self.__mid

                    # send packet
                    self.__log_debug("> %s", packet)
                    self.__rtp_history[
                        packet.sequence_number % RTP_HISTORY_SIZE
                    ] = packet
                    packet_bytes = packet.serialize(self.__rtp_header_extensions_map)
                    await self.transport._send_rtp(packet_bytes)

                    self.__ntp_timestamp = clock.current_ntp_time()
                    self.__rtp_timestamp = packet.timestamp
                    self.__octet_count += avpacket.size
                    self.__packet_count += 1
                    sequence_number = uint16_add(sequence_number, 1)
        except (asyncio.CancelledError, ConnectionError, MediaStreamError):
            pass
        except Exception:
            # we *need* to set __rtp_exited, otherwise RTCRtpSender.stop() will hang,
            # so issue a warning if we hit an unexpected exception
            self.__log_warning(traceback.format_exc())

        # stop track
        if self.__track:
            self.__track.stop()
            self.__track = None

        self.__log_debug("- RTP finished")
        self.__rtp_exited.set()



    def __log_debug(self, msg: str, *args) -> None:
        logger.debug(f"AVRTCRtpSender(%s) {msg}", self.__kind, *args)

    def __log_warning(self, msg: str, *args) -> None:
        logger.warning(f"AVRTCRtpsender(%s) {msg}", self.__kind, *args)