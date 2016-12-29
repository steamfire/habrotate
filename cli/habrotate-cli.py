# Copyright 2014 (C) Philip Crump
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

print "##### HABrotate #####"

from time import sleep, gmtime, strftime, mktime, time # For delays
import serial
import earthmaths # Az/El calculations
from socket import socket, AF_INET, SOCK_DGRAM # UDP PstRotator interface
from dateutil import parser
from json import load
from urllib2 import urlopen
from sys import exit, exc_info
from operator import itemgetter

def load_listener_config(config):
    if config["station_altitude"]=="auto":
        station_alt = google_elevation(float(config["station_latitude"]), float(config["station_longitude"]))
        return (float(config["station_latitude"]), float(config["station_longitude"]), float(station_alt))
    else:
        return (float(config["station_latitude"]), float(config["station_longitude"]), float(config["station_altitude"]))

def load_udp_config(config):
    return (str(config["udp_ip"]), int(config["udp_port"]))
    
def load_serial_config(config):
	return (str(config["serial_device"]), int(config["serial_baud"]))

def load_control_config(config):
    return (int(config["hysteresis"]), int(config["overshoot"]))

def google_elevation(lat, lon):
    elevation_json = urlopen('http://maps.googleapis.com/maps/api/elevation/json?locations=' + str(lat) + ',' + str(lon) + '&sensor=true')
    return round(load(elevation_json)['results'][0]['elevation'])

def grab_flights():
    i=0
    flights_string=''
    flights_op = []
    try:
        #flights_json = urlopen('http://habitat.habhub.org/habitat/_design/flight/_view/end_start_including_payloads?startkey=[' + str(int(time())) + ']&include_docs=True')
        flights_json = urlopen('http://habitat.habhub.org/habitat/_design/flight/_view/unapproved_name_including_payloads?startkey=[' + str(int(time())) + ']&include_docs=True')

    except:
        print "ERROR: Habitat HTTP Connection Error: ", exc_info()[0]
        exit(1)
    flights = load(flights_json)['rows']
    for flight in flights:
        if(flight['doc']['type']=="flight"):
            flights_op.append(dict())
            flights_op[i]["name"] = flight["doc"]["name"]
            flights_op[i]["id"] = flight["doc"]["_id"]
            flights_op[i]["time"] = mktime(parser.parse(flight["doc"]["launch"]["time"]).timetuple())
            i=i+1
            #flights_string += "{0},{2},{1};".format(flight["doc"]["_id"], flight["doc"]["launch"]["time"], flight["doc"]["name"])
    #return flights_string
    return sorted(flights_op, key=itemgetter('time'), reverse=True)
    
def grab_launch_position(flight_id):
    ## Get a list of the payloads in the flight
#    flights_json = urlopen('http://habitat.habhub.org/habitat/_design/flight/_view/end_start_including_payloads?startkey=[' + str(int(time())) + ']&include_docs=True')
    flights_json = urlopen('http://habitat.habhub.org/habitat/_design/flight/_view/unapproved_name_including_payloads?startkey=[' + str(int(time())) + ']&include_docs=True')
    flights = load(flights_json)['rows']
    for flight in flights:
        if(flight["doc"]["type"]=="flight" and flight["doc"]["_id"]==flight_id):
            launch_location = flight["doc"]["launch"]["location"]
    if "altitude" in launch_location:
        pass
    else:
        launch_location["altitude"] = google_elevation(launch_location["latitude"],launch_location["longitude"])
    return launch_location
    
def grab_position(flight_id):
    ## Get a list of the payloads in the flight
#    flights_json = urlopen('http://habitat.habhub.org/habitat/_design/flight/_view/end_start_including_payloads?startkey=[' + str(int(time())) + ']&include_docs=True')
    flights_json = urlopen('http://habitat.habhub.org/habitat/_design/flight/_view/unapproved_name_including_payloads?startkey=[' + str(int(time())) + ']&include_docs=True')

    flights = load(flights_json)['rows']
    for flight in flights:
        if(flight["doc"]["type"]=="flight" and flight["doc"]["_id"]==flight_id):
            payloads = flight["doc"]["payloads"]
    #print payloads
    ## Grab telemetry data for each payload
    flight_telemetry = []
    i=0
    for payload_id in payloads:
        telemetry_json = urlopen('http://habitat.habhub.org/habitat/_design/payload_telemetry/_view/flight_payload_time?startkey=["' + flight_id + '","' + payload_id + '",[]]&endkey=["' + flight_id + '","' + payload_id + '"]&include_docs=True&descending=True&limit=1')
        telemetry = load(telemetry_json)['rows']
        telemetry_list = list(telemetry)
        if len(telemetry_list)==0:
            continue
        last_string = sorted(telemetry_list, key=lambda x: x["doc"]["data"]["_parsed"]["time_parsed"])[-1]
        if '_fix_invalid' not in last_string["doc"]["data"]:
            flight_telemetry.append(dict())
            flight_telemetry[i]["latitude"] = last_string["doc"]["data"]["latitude"];
            flight_telemetry[i]["longitude"] = last_string["doc"]["data"]["longitude"];
            flight_telemetry[i]["altitude"] = last_string["doc"]["data"]["altitude"];
            flight_telemetry[i]["time"] = last_string["doc"]["data"]["time"];
            flight_telemetry[i]["sentence_id"] = last_string["doc"]["data"]["sentence_id"];
            flight_telemetry[i]["payload"] = last_string["doc"]["data"]["payload"];
            i=i+1
        else:
            # Fix invalid so grab 100 and look
            print "Last position is invalid, grabbing last 200 strings to look for valid one.."
            telemetry_json = urlopen('http://habitat.habhub.org/habitat/_design/payload_telemetry/_view/flight_payload_time?startkey=["' + flight_id + '","' + payload_id + '",[]]&endkey=["' + flight_id + '","' + payload_id + '"]&include_docs=True&descending=True&limit=200')
            telemetry = load(telemetry_json)['rows']
            telemetry_list = list(telemetry)
            if len(telemetry_list)==0:
                continue
            strings = sorted(telemetry_list, key=lambda x: x["doc"]["data"]["_parsed"]["time_parsed"], reverse=True)
            fix_invalid = True
            for last_string in strings:
                if '_fix_invalid' in last_string["doc"]["data"]:
                    continue
                flight_telemetry.append(dict())
                flight_telemetry[i]["latitude"] = last_string["doc"]["data"]["latitude"];
                flight_telemetry[i]["longitude"] = last_string["doc"]["data"]["longitude"];
                flight_telemetry[i]["altitude"] = last_string["doc"]["data"]["altitude"];
                flight_telemetry[i]["time"] = last_string["doc"]["data"]["time"];
                flight_telemetry[i]["sentence_id"] = last_string["doc"]["data"]["sentence_id"];
                flight_telemetry[i]["payload"] = last_string["doc"]["data"]["payload"];
                i=i+1
                break
    ## Get latest timed position
    try:
        latest_telemetry = sorted(flight_telemetry, key=lambda x: x["time"])[-1]
    except (KeyError, IndexError):
        launch_location = grab_launch_position(flight_id)
        return {"Not launched": "1", "latitude": launch_location["latitude"], "longitude": launch_location["longitude"], "altitude": launch_location["altitude"]}
    if latest_telemetry["latitude"] == latest_telemetry["longitude"]:
        return {"Error":"1","Message":"No Valid Position Telemetry Found"}
    try:
        return {"latitude": latest_telemetry["latitude"], "longitude": latest_telemetry["longitude"], "altitude": latest_telemetry["altitude"], "sentence_id": latest_telemetry["sentence_id"], "payload": latest_telemetry["payload"], "time": latest_telemetry["time"]}
    except KeyError:
        return {"Error":"1","Message":"Position does not have required fields????"}
        
print "Parsing config.json.."
        
try:        
    config_file = open('config.json', 'r')
except IOError:
    print "ERROR: Config File 'config.json' does not exist in application directory."
    exit(1)
try:
    config_json = load(config_file)
except:
    print "ERROR: Syntax Error in config.json file."
    exit(1)

config_file.close()

# strFlights ='http://habitat.habhub.org/habitat/_design/flight/_view/end_start_including_payloads?startkey=[' + str(int(time())) + ']&include_docs=True'
strFlights ='http://habitat.habhub.org/habitat/_design/flight/_view/unapproved_name_including_payloads?startkey=[' + str(int(time())) + ']&include_docs=True'
listener = load_listener_config(config_json)
print("Receiver Station Location: Lat: " + str(listener[0]) + " Lon: " + str(listener[1]) + " Altitude: " + str(listener[2]))

udp_config = load_udp_config(config_json)
print("UDP Configuration: IP: " + str(udp_config[0]) + " Port: " + str(udp_config[1]))

serial_config = load_serial_config(config_json)
print("Serial Configuration: " + str(serial_config[0]) + " Baud: " + str(serial_config[1]))

control_config = load_control_config(config_json)
hysteresis = control_config[0]
overshoot = control_config[1]
if overshoot >= hysteresis: #If overshoot is larger than hysteresis we will oscillate
    print ("ERROR: Overshoot must be less than the Hysteresis, else oscillation may occur.")
    exit(1)
print ("Control Configuration: Hysteresis = " + str(control_config[0]) + " degrees, Overshoot = " + str(control_config[1]) + " degrees.")

i=0
ids=[25]

print "Querying flights.."

for flight in grab_flights():
    i=i+1
    ids.append(flight["id"])
    if strftime("%d:%m", gmtime(int(flight["time"]))) == strftime("%d:%m", gmtime()):
        print "{0}: {1} - TODAY".format(i, flight["name"].encode('utf-8'))
    else:
        print "{0}: {1}".format(i, flight["name"].encode('utf-8'))

valid_input = False
while not valid_input:
    try:
        wanted_id = int(raw_input('Select Flight number: '))
        if wanted_id==0:
            raise IndexError
        flight_id = ids[wanted_id]
        valid_input = True
    except ValueError:
        print "Input not an integer, please try again:"
    except IndexError:
        print "Input out of range, please try again:"


udp_socket = socket( AF_INET, SOCK_DGRAM ) # Open UDP socket
ser = serial.Serial(str(serial_config[0]), str(serial_config[1]))
print(ser.name)

loopcount = 0
update_rotator = 0
try:
    while True:
        print "Querying position.."
        position_data = grab_position(flight_id)

        if "Error" in position_data:
            print("ERROR: " + str(position_data["Message"]))
            sleep(10)
            continue
        try:
            balloon = (position_data["latitude"], position_data["longitude"], position_data["altitude"])
            if "Not launched" in position_data: # No telemetry data, position is launch site
                print "Found Launch site at " + repr(balloon) + ". Balloon position will be used as soon as it is uploaded."
            else:
                print 'Found "' + position_data["payload"].encode('utf-8') + '" at ' + repr(balloon) + " Sentence: " + str(position_data["sentence_id"]) + " at " + position_data["time"] + " UTC."
        except:
            print "ERROR: Document Parsing Error:", exc_info()[0]
            print "DEBUG info:"
            print position_data
            sleep(10)
            continue

        p = earthmaths.position_info(listener, balloon)
        bearing = round(p["bearing"])
        elevation = round(p["elevation"])
        distance = round(p["straight_distance"]/1000,1)
        print("Balloon Azimuth: " + str(bearing) + " Elevation: " + str(elevation) + " at " + str(distance) + " km.")
        if loopcount == 0: #Set rotator on first loop
            sleep(10)
            rotator_bearing = bearing
            rotator_elevation = elevation
            print("Moving rotator to Azimuth: " + str(rotator_bearing) + " Elevation: " + str(rotator_elevation))
            udp_string = "<PST><TRACK>0</TRACK><AZIMUTH>" + str(rotator_bearing) + "</AZIMUTH><ELEVATION>" + str(rotator_elevation) + "</ELEVATION></PST>"
            #serial_string = str(rotator_bearing) + " " + str(rotator_elevation) + "\n"
            serial_string = str(rotator_bearing) + " " + "85" + "\n"
            udp_socket.sendto(udp_string, udp_config)
            print(serial_string + "\n")
            ser.write(serial_string)
        else:
            if bearing > (rotator_bearing + hysteresis):
                rotator_bearing = (bearing + overshoot)%360
                update_rotator = 1
            elif bearing < (rotator_bearing - hysteresis):
                rotator_bearing = (bearing - overshoot)%360
                update_rotator = 1
            if elevation > (rotator_elevation + hysteresis):
                rotator_elevation = elevation + overshoot
                update_rotator = 1
            elif elevation < (rotator_elevation - hysteresis):
                rotator_elevation = elevation - overshoot
                update_rotator = 1
            if update_rotator == 1:
                update_rotator = 0
                print("Moving rotator to Azimuth: " + str(rotator_bearing) + " Elevation: " + str(rotator_elevation))
                udp_string = "<PST><TRACK>0</TRACK><AZIMUTH>" + str(rotator_bearing) + "</AZIMUTH><ELEVATION>" + str(rotator_elevation) + "</ELEVATION></PST>"
                # serial_string = str(rotator_bearing) + " " + str(rotator_elevation) + "\n"
                serial_string = str(rotator_bearing) + " " + "85" + "\n"
                udp_socket.sendto(udp_string, udp_config)
                print(serial_string + "\n")
                ser.write(serial_string)
            else:
                print ("Current Rotator offset: Azimuth: " + str(rotator_bearing-bearing) + " Elevation: " + str(rotator_elevation-elevation) + ", holding.")
        print("Pausing for 10s...")
        sleep(10)
        loopcount+=1
except KeyboardInterrupt:
	ser.close()
	print '^C received, Shutting down.'
