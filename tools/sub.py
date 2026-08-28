import time, paho.mqtt.client as mqtt

HOST="beta.salvilighting.com"; PORT=443
USER="gw-beta"; PASS="uTohQA5M5sHki#VJFt6mYj#"

c=mqtt.Client(transport="websockets")
c.username_pw_set(USER,PASS); c.tls_set(); c.tls_insecure_set(True); c._protocol=mqtt.MQTTv311
def on_connect(cli,ud,flags,rc): print("CONNECT rc=",rc)
def on_disconnect(cli,ud,rc): print("DISCONNECT rc=",rc)
c.on_connect=on_connect; c.on_disconnect=on_disconnect
c.connect(HOST,PORT,30); c.loop_forever()
