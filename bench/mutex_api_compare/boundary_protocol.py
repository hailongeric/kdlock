"""Bounded replies for a quiescent diagnostic hold, never an unlock ACK."""
import json
import hashlib
import os
import select
import time


def receive(fd, seconds=210, maximum=2*1024*1024):
    deadline = time.monotonic()+seconds
    data = bytearray()
    while True:
        remaining = deadline-time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            raise TimeoutError('boundary coordination timed out; no drain inferred')
        piece = os.read(fd, min(65536, maximum+1-len(data)))
        if not piece:
            raise ValueError('boundary coordination EOF')
        data.extend(piece)
        if len(data) > maximum:
            raise ValueError('boundary reply too large')
        if b'\n' in piece:
            if not data.endswith(b'\n') or data.count(b'\n') != 1:
                raise ValueError('boundary reply must be one complete JSON line')
            return json.loads(data)


def host_hash(host):
    return hashlib.sha256(json.dumps(host, sort_keys=True).encode()).hexdigest()


def validate_reply(reply, token):
    if not isinstance(reply, dict) or set(reply) != {'boundary_ack', 'boundary_token', 'host_state', 'observations'}:
        raise ValueError('unexpected boundary reply fields')
    if type(reply['boundary_ack']) is not int or reply['boundary_ack'] != 1 or reply['boundary_token'] != token or not isinstance(reply['host_state'], dict):
        raise ValueError('unexpected boundary sequence or host state')
    if not isinstance(reply['observations'], list) or not 1 <= len(reply['observations']) <= 5:
        raise ValueError('missing or excessive boundary observations')
    previous = 0
    for index, observation in enumerate(reply['observations']):
        if (observation['capture'] != f'boundary-{token}-{index}' or
                not previous < observation['capture_began_ns'] <= observation['capture_finished_ns'] or
                not observation['boundary_marker_ns'] <= observation['capture_began_ns'] or
                not observation['request_sent_ns'] <= observation['ack_received_ns']):
            raise ValueError('boundary capture identity or ordering differs')
        previous = observation['capture_finished_ns']
    if reply['observations'][-1]['host_sha256'] != host_hash(reply['host_state']):
        raise ValueError('selected host is not the last retained boundary capture')
    return reply
