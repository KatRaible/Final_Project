#
# National Rail Open Data client demonstrator
# Copyright (C)2019-2022 OpenTrainTimes Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
import os
import stomp
import zlib
import io
import time
import socket
import logging
import json

from confluent_kafka import Producer

logging.basicConfig(format='%(asctime)s %(levelname)s\t%(message)s', level=logging.DEBUG)

try:
    import PPv16
except ModuleNotFoundError:
    logging.error("Class files not found - please configure the client following steps in README.md!")

USERNAME = os.getenv('USERNAME', 'DARWIN3dfd20f5-1421-44b9-9c8b-c6a1198a4792')
PASSWORD = os.getenv('PASSWORD', 'ecac12cc-6937-42fd-b136-5345fc7387cb')
HOSTNAME = os.getenv('HOSTNAME', 'darwin-dist-44ae45.nationalrail.co.uk')
HOSTPORT = int(os.getenv('HOSTPORT', '61613')) 
TOPIC = os.getenv('TOPIC', 'darwin.pushport-v16')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'open_rail')

CLIENT_ID = socket.getfqdn()
HEARTBEAT_INTERVAL_MS = int(os.getenv('HEARTBEAT_INTERVAL_MS', '15000'))
RECONNECT_DELAY_SECS = int(os.getenv('RECONNECT_DELAY_SECS', '15'))

if USERNAME == '':
    logging.error("Username not set - please configure your username and password in opendata-nationalrail-client.py!")
    
def produce_to_kafka(topic, key=None, value=None):
    conf = {'bootstrap.servers': "broker:9092",
             'client.id': socket.gethostname()}

    if value:
        value = json.dumps(value)\
                    .encode('utf-8')
    
    producer = Producer(conf)
    producer.poll(1)
    producer.produce(topic=topic,
                    key=key,
                    value=value
                    )
    
    producer.flush()


def connect_and_subscribe(connection):
    if stomp.__version__[0] < 5:
        connection.start()

    connect_header = {'client-id': USERNAME + '-' + CLIENT_ID}
    subscribe_header = {'activemq.subscriptionName': CLIENT_ID}

    connection.connect(username=USERNAME,
                       passcode=PASSWORD,
                       wait=True,
                       headers=connect_header)

    connection.subscribe(destination=TOPIC,
                         id='1',
                         ack='auto',
                         headers=subscribe_header)


class StompClient(stomp.ConnectionListener):

    def on_heartbeat(self):
        logging.info('Received a heartbeat')

    def on_heartbeat_timeout(self):
        logging.error('Heartbeat timeout')

    def on_error(self, headers, message):
        logging.error(message)

    def on_disconnected(self):
        logging.warning('Disconnected - waiting %s seconds before exiting' % RECONNECT_DELAY_SECS)
        time.sleep(RECONNECT_DELAY_SECS)
        exit(-1)

    def on_connecting(self, host_and_port):
        logging.info('Connecting to ' + host_and_port[0])

    def on_message(self, frame):
        logging.info(frame)
        try:
            logging.info('Message sequence=%s, type=%s received', frame.headers['SequenceNumber'],
                        frame.headers['MessageType'])
            bio = io.BytesIO()
            bio.write(str.encode('utf-16'))
            bio.seek(0)
            msg = zlib.decompress(frame.body, zlib.MAX_WBITS | 32)
            # logging.debug(msg)
            obj = PPv16.CreateFromDocument(msg)
            logging.info("Successfully received a Darwin Push Port message from %s", obj.ts)            

            # Instead of parsing the XML, we just send it to Kafka
            # We also encode the XML content to 'utf-8' to ensure Kafka compatibility

            produce_to_kafka(topic=KAFKA_TOPIC,
                            key=frame.headers['SequenceNumber'],
                            value=msg.decode('utf-8')  # Encode the XML content to 'utf-8'
                            )
            
            logging.info(f'Sent Event to Kafka Topic: {KAFKA_TOPIC}')
            
        except Exception as e:
            logging.error(str(e))

conn = stomp.Connection12([(HOSTNAME, HOSTPORT)],
                          auto_decode=False,
                          heartbeats=(HEARTBEAT_INTERVAL_MS, HEARTBEAT_INTERVAL_MS))

conn.set_listener('', StompClient())
connect_and_subscribe(conn)

while True:
    time.sleep(1)

conn.disconnect()
