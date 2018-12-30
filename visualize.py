#!/usr/bin/env python3
# encoding: utf-8
# Needs following packages:
# check requirements.txt
# Just enter sudo pip install --upgrade -r requirements.txt

import os
import json
import time
import socket
import logging
import argparse
import paramiko
import regex as re
from random import choice
from datetime import datetime
from configparser import ConfigParser

def anfangssachen():
	parser = argparse.ArgumentParser(
	prog='',
	description='''SNMP replacement for SSH, Reads various data from HP unified 870 controllers''',
	epilog='''created by Heiko Borchers for the Heinrich Heine University Duesseldorf''')
	parser.add_argument("--test", "-t", help="Testmode without Controller (reads information from textfiles)", action="store_true")
	parser.add_argument("--version","-v", help="shows script version", action="store_true")
	parser.add_argument("--basic", "-b", help="reads the most basic data about the access points", action='store_true')
	parser.add_argument("--spectrum", "-s", help="reads the spectrum data (not useful without -b)", action='store_true')
	parser.add_argument("--clients", "-c", help="Reads the client data", action='store_true')
	parser.add_argument("--all", "-a", help="Reads all data the script was made for", action='store_true')
#	Not jet implemented
#	parser.add_argument("--config", "-c", help="Enter a Path to your configuration file", action="store_true")
	args = parser.parse_args()
	return args

class configuration():
	#Liest die Configuration mit Nutzernamen und Passwörtern mittels Configparser erstellt ein Config Objekt
	def __init__(self):
		self.username  = None
		self.password = None
		self.config_ip_1 = None
		self.config_ip_2 = None
		self.config_ip_3 = None
		self.logging_host = None
		self.logging_port = None
		self.logging_directory = None

	def add_config(self):
		config = ConfigParser()
		if args.test == False:
			settings_files = {('settings.conf.demo',True),('settings.conf',False),('/etc/settings.conf',False),('/usr/etc/settings.conf',False)}
			for item in settings_files:
				if os.path.isfile(item[0]):
					config.read(item[0])
					args.test=item[1]
		else:
			config.read("settings.conf.demo")
			print("Running in Demo Mode")

		self.username = config.get('login', 'username')
		self.password = config.get('login', 'password')
		self.config_ip_1 = config.get('addresses', 'config_ip_one')
		if config.has_option('addresses', 'config_ip_two'):
			self.config_ip_2 = config.get('addresses', 'config_ip_two')
		if config.has_option('addresses', 'config_ip_three'):
			self.config_ip_2 = config.get('addresses', 'config_ip_three')
		self.logging_host = config.get('logging', 'hostname')
		self.logging_port = config.getint('logging', 'port')
		if args.test == False:
			self.logging_directory = config.get('folders', 'log_dir')
		else:
			self.logging_directory = "."

	def gib_config_aus(self):
		return self

class Wlan:
	def __init__(self,newname):
		self.name = newname
		self.allcontroller = {}

	def addcontroller(self,name,ip):
		self.allcontroller[name] = Controller(ip)

	def starte_ssh_verbindung(self):
		for controller in self.allcontroller:
			self.allcontroller[controller].starte_ssh_verbindung()

	def daten_einlesen(self, ssh_befehl):
		for controller in self.allcontroller:
			self.allcontroller[controller].daten_einlesen(ssh_befehl)

	def gib_anzahl_ap_aus(self):
		for controller in self.allcontroller:
			print("Anzahl AP von "+controller+":"+str(self.allcontroller[controller].anzahl_ap()))

	def clients_einlesen(self):
	#Wir brauchen ja nur einen Controller nach den clients fragen, also nehmen wir einen zufälligen
	#Würden wir beide Controller fragen wäre die Script Laufzeit doppelt so lang
		specific_controller = choice(list(self.allcontroller.values()))
		specific_controller.daten_einlesen('clients')

	def ap_list_to_json_files(self):
	#Funktion um aus der AP Liste JSON Dateien für jeden AP zu generieren.
		for controller in self.allcontroller:
			self.allcontroller[controller].ap_list_to_json_files()

	def ap_list_to_splunk(self):
	#Pusht die Liste mit APs an einen Splunk Server
		for controller in self.allcontroller:
			self.allcontroller[controller].ap_list_to_splunk()

	def beende_ssh_verbindung(self):
	#Beendet die offenen SSH Verbindungen aller Controller
		for controller in self.allcontroller:
			self.allcontroller[controller].beende_ssh_verbindung()

	def gib_controller_namen_aus(self):
		return self.name

class Netzgerät:
	def __init__(self, ip, mac=None):
		self.ip = ip
		self.mac = mac
		self.geraetetype = None
		self.sshsh = None
		self.ssh = None
		self.cmd_finished = None
		self.ssh_connection_active = False

	def gib_mac_aus(self):
		print (self.mac)
		return

	def gib_ip_aus(self):
		return self.ip

	def starte_ssh_verbindung(self):
	#Startet eine SSH Verbindung zum gewählten Controller
		logging.info("Starte SSH Verbindung zu "+self.ip)
		#self.geraetetype = "hp870"
		if (self.geraetetype == "hp870"):
			self.cmd_finished = re.compile(r"<Unified_")
			screen_disable_cmd = "screen-length disable"
			self.cmd_any_key_to_continue = re.compile(r"Press any key to continue")
			self.strange_to_ascii = re.compile(r'\x1b\[[^@-_\x1b]*[@-_a-z]')
		try:
			self.ssh = paramiko.SSHClient()
			self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
			self.ssh.connect(self.ip, username=config_data.username, password=config_data.password, allow_agent=False, look_for_keys=False)
			self.sshsh = self.ssh.invoke_shell()
		except Exception as e:
			print("Verbindung nicht möglich:"+str(e))
			exit()
		self.ssh_connection_active = True
		time.sleep(0.5)
		output_raw = self.sshsh.recv(10000).decode("utf-8")
		output_list = output_raw.split('\r\n')
		for line in output_list:
			if (self.cmd_any_key_to_continue.search(line)):
				self.sshsh.send("p")
				time.sleep(1) #Ansonsten funktioniert manchmal der nachfolgende Befehl nicht
		if (not self.cmd_finished):
			time.sleep(1)
		self.sshsh.send(screen_disable_cmd+"\n")
		time.sleep(1)
		self.sshsh.send(screen_disable_cmd+"\n")
		time.sleep(0.5)
		output_raw = self.sshsh.recv(1000).decode("utf-8")
		if (not self.cmd_finished):
			hostname = self.get_hp_switch_hostname_from_output(output_raw)
			self.cmd_finished = re.compile(r"{}".format(hostname))
		logging.info("Initialisierung der SSH-Verbindung erfolgreich")

	def beende_ssh_verbindung(self):
		logging.info("Beende SSH Verbindung zu "+self.ip)
		ssh_connection_active = False

	def ssh_befehl(self,befehl):
		if (not self.ssh_connection_active): #Sofern keine aktive SSH-Session besteht, macht diese Funktion keinen Sinn
			logging.error("Kann Befehl: "+befehl+" nicht ausführen, da keine SSH-Verbindung besteht.")
			return False
		logging.info("Führe SSH-Befehl "+befehl+" auf Controller: " + self.ip +" aus")
		self.sshsh.send(befehl+"\n")
		time.sleep(0.5)
		logging.debug("Reading input 2000 bytes")
		output_raw = self.sshsh.recv(2000).decode("utf-8")
		output_list = output_raw.split('\n\r')
		while not self.cmd_finished.search(output_list[-1]):
			logging.debug("Reading input 5000 bytes more")
			output_new = self.sshsh.recv(5000).decode("utf-8")
			output_list = output_new.split('\n')
			output_raw += output_new #Raw-Output wird so lange addiert, bis letzte Zeile HP-Unified ist
		nice_output = []
		output_list = output_raw.split('\n')
		for line in output_list[2:-2]: #Output von Steuerzeichen befreien und erstes und letztes Element nicht anzeigen
			nice_output.append(self.strange_to_ascii.sub('',line))
		return nice_output

class Controller(Netzgeraet):
	def __init__(self, ip):
		self.ip = ip
		super(Netzgeraet, self).__init__()
		self.geraetetype = "hp870"
		self.aps_name = {}
		self.clients_name = {}

	def wlan_tabellen_parser(self, raw_table, heads):
		output_table = []
		for line in raw_table:
			if (heads > 0): heads -= 1
			else:
				if not line.startswith("--"): #Entfernt die Linien zwischen den einzelnen APs
					line = re.sub(r"\s{2,}", ',', line) #Ersetzt zwei oder mehr Leerzeichen durch ein Komma
					line = re.sub(r"\s", '', line) #Entfernt einzelne Leerzeichen
					ap = line.split(",") #Sorgt für eine Trennung der Strings am Komma
					if not (len(ap) <= 3 or ap[0] == "APName"):
						output_table.append(ap)
		return(output_table)


	def client_tabellen_parser(self, raw_table, heads):
#		output_table = [] #Erstellt eine leere Tabelle in die alle Clients kommen
		client_terminator = 0 #Laufvariable um Clients sauber zu trennen
		single_client = [] #Erstellt eine Leere Tabelle mit einem Client
		for line in raw_table:
			if (heads > 0):
				heads -= 1
			else:
				if (line.startswith("--")):
					client_terminator = client_terminator + 1
				else:
					single_client.append(line)
				if client_terminator == 2:
					client = Client(single_client)
					client.parse_data(single_client)
					single_client = []
					client_terminator = 0
		return(single_client)

	def daten_einlesen(self, ssh_command):
	#Funktion um die SSH Befehle zu zu parsen und einfachere Erweiterung zu ermöglichen
		if ssh_command == "basic":
			self.basisdaten_einlesen()
		elif ssh_command == "spectrum":
			self.spectrum_einlesen()
		elif ssh_command == "clients":
			self.clients_einlesen()
		else:
			print("Option "+ ssh_command +" (noch) nicht verfügbar.")


	def basisdaten_einlesen(self):
		line = 10 #Filtert die ersten "unnötigen" Daten
		lines = 0
		if args.test:
			output = open('ap_basic_demo.txt', 'r', encoding='utf-8')
		else:
			output = self.ssh_befehl("display wlan ap all")
		basic_table = self.wlan_tabellen_parser(output, line)
		for line in basic_table:
			lines += 1
			self.add_ap_basic_data(line)
		print(lines)

	def spectrum_einlesen(self):
		line = 3 #Filtert die ersten "unnötigen" Daten
		lines = 0
		if args.test:
			output = open('ap_spectrum_demo.txt', 'r', encoding='utf-8')
		else:
			output = self.ssh_befehl("display wlan spectrum-analysis channel-quality")
		basic_table = self.wlan_tabellen_parser(output,line)
		for line in basic_table:
			lines += 1
			self.add_ap_spectrum_data(line)
		print(lines)

	def clients_einlesen(self):
		line = 1
		print(datetime.now())
		if args.test:
			output = open('client_demo.txt', 'r', encoding='utf-8')
		else:
			output = self.ssh_befehl("display wlan client verbose")
		print(datetime.now())
		#basic_table = self.client_tabellen_parser(output,line)
		self.client_tabellen_parser(output, line)
		print(datetime.now())



	def add_ap_basic_data(self, data):
	#Fügt die Basis Daten zum AP-Objekt hinzu
		if data[0] not in self.aps_name:
			self.create_ap(data[0])
		self.aps_name[data[0]].add_status(data[1])
		self.aps_name[data[0]].add_model(data[2])
		self.aps_name[data[0]].add_serial(data[3])
		self.aps_name[data[0]].add_measurement_timestamp()
		if self.ip == config_data.config_ip_1:
			self.aps_name[data[0]].add_controller("Unified_Sued")
		if self.ip == config_data.config_ip_2:
			self.aps_name[data[0]].add_controller("Unified_Nord")

	def add_ap_spectrum_data(self, data):
		if data[0] not in self.aps_name:
				logging.error("AP: " + data[0] +" auf Controller: " + self.ip +" nicht gefunden")
		else:
			if data[2]:
				if data[1] == '1':
					self.aps_name[data[0]].add_channel_5ghz(data[2])
					self.aps_name[data[0]].add_avg_air_quality_5ghz(data[3])
					self.aps_name[data[0]].add_minimum_air_quality_5ghz(data[4])
					self.aps_name[data[0]].add_interference_5ghz(data[5])
				if data[1] == '2':
					self.aps_name[data[0]].add_channel_2_4ghz(data[2])
					self.aps_name[data[0]].add_avg_air_quality_2_4ghz(data[3])
					self.aps_name[data[0]].add_minimum_air_quality_2_4ghz(data[4])
					self.aps_name[data[0]].add_interference_2_4ghz(data[5])

	def display_geraetetyp(self):
		return self.geraetetype

	def create_ap(self,serial):
		self.aps_name[serial] = AccessPoint(serial)

	def create_clients(self,name):
		self.clients_name[name] = Client(name)

	def gib_serials_aus(self):
		for ap in self.aps_name:
			print(self.aps_name[ap].show_serial())
		return

	def anzahl_ap(self):
		return(len(self.aps_name.keys()))

	def anzahl_clients(self):
		return (len(self.clients_name.keys()))

	def print_client_data(self):
		for client in self.clients_name:
			print(self.clients_name[client].__dict__)

	def print_ap_data(self):
		for ap in self.aps_name:
			print(self.aps_name[ap].__dict__)
		return

	def ap_list_to_json_files(self):
		subdirectory = 'AccessPoints'
		if not os.path.exists(config_data.logging_directory +"/"+ subdirectory):
			os.makedirs(config_data.logging_directory +"/"+ subdirectory)
		for ap in self.aps_name:
			ap_object = self.aps_name[ap].__dict__
			dirty_filename = ap_object['serial'] + ".json"
			filename = dirty_filename.replace("\"", "")
			filename = filename.replace("/", "")
			temp = open(os.path.join(config_data.logging_directory, subdirectory, filename), 'w')
			temp.write(json.dumps(self.aps_name[ap].__dict__))
			temp.close()

	def ap_list_to_splunk(self):
		for ap in self.aps_name:
			self.aps_name[ap].to_splunk()

class AccessPoint:
	def __init__(self, ap):
		self.APName  = ap
		self.ip = None
		self.status = None
		self.model = None
		self.serial = None
		self.controller = None
		self.avg_air_quality_2_4ghz = None
		self.avg_air_quality_5ghz = None
		self.minimum_air_quality_2_4ghz = None
		self.minimum_air_quality_5ghz = None
		self.channel_2_4ghz = None
		self.interference_2_4ghz = None
		self.interference_5ghz = None
		self.measurement_timestamp = None

	def add_status(self, status):
		self.status = status

	def add_model(self, model):
		self.model = model

	def add_serial(self,serial):
		self.serial = serial

	def add_controller(self, controller):
		self.controller = controller

	def add_avg_air_quality_2_4ghz(self, avg_air_quality_2_4ghz):
		self.avg_air_quality_2_4ghz = avg_air_quality_2_4ghz

	def add_avg_air_quality_5ghz(self, avg_air_quality_5ghz):
		self.avg_air_quality_5ghz = avg_air_quality_5ghz

	def add_minimum_air_quality_2_4ghz(self, minimum_air_quality_2_4ghz):
		self.minimum_air_quality_2_4ghz= minimum_air_quality_2_4ghz

	def add_minimum_air_quality_5ghz(self, minimum_air_quality_5ghz):
		self.minimum_air_quality_5ghz = minimum_air_quality_5ghz

	def add_channel_2_4ghz(self, channel_2_4ghz):
		self.channel_2_4ghz = channel_2_4ghz

	def add_channel_5ghz(self, channel_5ghz):
		self.channel_5ghz = channel_5ghz

	def add_interference_2_4ghz(self,interference_2_4ghz):
		self.interference_2_4ghz = interference_2_4ghz

	def add_interference_5ghz(self,interference_5ghz):
		self.interference_5ghz = interference_5ghz

	def add_measurement_timestamp(self):
		self.measurement_timestamp = str(datetime.now())

	def show_serial(self):
		return self.serial

	def show_controller(self):
		return self.controller

	def gib_namen_aus(self):
		print (self.APName)
		return

	def gib_ip_aus(self):
		print (self.ip)
		return

	def to_json(self):
		ap_object = json.dumps(self.__dict__)
		return ap_object

	def to_json_file(self):
		subdirectory = 'AccessPoints'
		if not os.path.exists(logging_directory + "/" + subdirectory):
			os.makedirs(subdirectory)
		dirty_filename = self.APName+".json"
		filename = dirty_filename.replace("/", "")
		temp = open(os.path.join(logging_directory, subdirectory, filename), 'a+')
		if not filename.is_file():
			temp.write(self.to_json()+"\n")
		temp.close()

	def to_splunk(self):
		splunk_objekt = bytes(self.to_json(), 'UTF-8')
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.connect((config_data.logging_host, config_data.logging_port))
		s.sendall(splunk_objekt)
		s.close()

class Client:
	def __init__(self, client):
		client = {}
		client_list = []

	def client_data_to_json(self, client):
		return json.dumps(client)

	def read_data(self, data):
		client = data
		return client

	def parse_data(self, data):
		single_client = {}
		for line in data:
			if ":" or r"\d{2}[,]\d{2}" in line:
				if not line.startswith('\r'):
					line = re.sub(r"\s{2,}", '', line)  # Ersetzt Gruppen von " " durch ":"
					line = re.sub(r"^\s", '', line)  # Entfernt einzelnes Leerzeichen am Anfang
					line = re.sub(r"\r$", '', line)
					line = re.sub("\n", '', line)
					line = re.sub(r"::", ":", line)
					#print(line)
					if line.find("Up Time") == -1:
						liste = line.split(":")
					else:
						liste = line.split("):")
						liste[0] = "Up Time"
#						print(single_client)
					regexp = re.compile(r"\d{2}[,]\d{2}")
					if regexp.search(line):
						#print("MCS Set Addition found")
						single_client["Support MCS Set"]+=line
					if len(liste)>1 and not line[1] == "ClientInformation":
						single_client.update({liste[0]:liste[1]})
		self.to_splunk(single_client)
		self.to_json_file(single_client)

	def to_json_file(self, single_client):
		subdirectory = 'clients'
		if not os.path.exists(config_data.logging_directory +"/"+ subdirectory):
			os.makedirs(config_data.logging_directory +"/"+subdirectory)
		dirty_filename = single_client["MAC Address"]+".json"
		filename = dirty_filename.replace("\s", "")
		temp = open(os.path.join(config_data.logging_directory, subdirectory, filename), 'w')
		temp.write(self.client_data_to_json(single_client)+"\n")
		temp.close()

	def to_splunk(self, single_client):
		if args.test == False:
			splunk_objekt = bytes(json.dumps(single_client), 'UTF-8')
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			s.connect((config_data.logging_host, config_data.logging_port))
			s.sendall(splunk_objekt)
			s.close()
		else:
			print("Function not available in testing mode")


def wlan_main():
	logging.info("********** wlan ********")
	unify = Wlan("Unify W-LAN")
	if args.test == False:
		unify.addcontroller("Unified_Nord",config_data.config_ip_1)
		unify.addcontroller("Unified_Sued",config_data.config_ip_2)
		unify.starte_ssh_verbindung()
	else:
		unify.addcontroller("Demo_Controller_1",config_data.config_ip_1)
		unify.addcontroller("Demo_Controller_2",config_data.config_ip_2)
	if args.basic == True or args.all == True:
		unify.daten_einlesen("basic")
	if args.spectrum == True or args.all == True:
		unify.daten_einlesen("spectrum")
	if args.clients == True or args.all == True:
		unify.clients_einlesen()
	unify.ap_list_to_json_files()
	if args.test == False:
		unify.ap_list_to_splunk
		unify.beende_ssh_verbindung()
	logging.info("wlan Ende")


if __name__ == "__main__":
	args = anfangssachen()
	if args.test == True:
		logging.basicConfig(format='%(asctime)s - %(message)s',level=logging.DEBUG)
		config = configuration.add_config(configuration)
		configuration.add_config(config)
		config_data = configuration.gib_config_aus(configuration)
	else:
		logging.basicConfig(format='%(asctime)s - %(message)s',level=logging.INFO)
		configuration.add_config(configuration)
		config_data = configuration.gib_config_aus(configuration)
	if args.version == True:
		print("Beta 0.1.0")
	else:
		wlan_main()
		logging.info("Ende")
