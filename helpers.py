import psycopg2, psycopg2.extras
import json
from systemd import journal
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from hashlib import sha256
from struct import pack
from os import urandom
from time import time

#from configuration import config

DEBUG = {'started' : False}

def generate_UID():
	return sha256(pack('f', time()) + urandom(16)).hexdigest()

def dCheck(d, key, val=None):
	if not key in d: return False
	if val and val is not d[key]: return False

	return d[key]

def signal_handler(signal, frame):
	remove(config['pidfile'])
	exit(0)

class postgres():
	def __init__(self):
		try:
			self.con = psycopg2.connect("dbname={db} user={user} password={passwd}".format(db=config['postgresql']['database'], user=config['postgresql']['username'], passwd=config['postgresql']['password']))
			self.cur = self.con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
		except psycopg2.OperationalError:
			con = psycopg2.connect("user={user} password={passwd}".format(db=config['postgresql']['database'], user=config['postgresql']['username'], passwd=config['postgresql']['password']))
			con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
			cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
			cur.execute("CREATE DATABASE {db};".format(db=config['postgresql']['database']))
			# con.commit() ## Redundant because we're in a isolated autocommit context.
			cur.close()
			con.close()

			self.con = psycopg2.connect("dbname={db} user={user} password={passwd}".format(db=config['postgresql']['database'], user=config['postgresql']['username'], passwd=config['postgresql']['password']))
			self.cur = self.con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

	def __enter__(self):
		## == TODO: Remove, these are just for testing purposes
		if not DEBUG['started']:
			## == Users (Crispy)
			self.cur.execute('DROP TABLE IF EXISTS users;')
			self.cur.execute('DROP TABLE IF EXISTS messages;')
		
		## == Players (GH)
		self.cur.execute("CREATE TABLE IF NOT EXISTS users (id BIGSERIAL PRIMARY KEY, uid VARCHAR(255) NOT NULL, name VARCHAR(255) NOT NULL, domain VARCHAR(255) NOT NULL, password VARCHAR(255) NOT NULL, owner VARCHAR(255) DEFAULT NULL, contact_info JSON NOT NULL DEFAULT '{}', last_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), CONSTRAINT one_player UNIQUE (name, owner));")
		self.cur.execute("CREATE INDEX IF NOT EXISTS name ON users (name);")
		self.cur.execute("CREATE INDEX IF NOT EXISTS uid ON users (uid);")
		self.cur.execute("CREATE TABLE IF NOT EXISTS messages (id BIGSERIAL PRIMARY KEY, uid VARCHAR(255) NOT NULL, owner VARCHAR(255) NOT NULL, message JSON NOT NULL DEFAULT '{}', created TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), CONSTRAINT one_team UNIQUE (uid));")
		self.cur.execute("CREATE INDEX IF NOT EXISTS uid ON messages (uid);")

		if not DEBUG['started']:
			## == Users (Crispy)
			## -- TODO: Remove, these are just for testing purposes.
			users = {'anton' : {'uid' : generate_UID(), 'domain' : 'hvornum.se', 'password' : 'test'}}

			for user in users:
				self.cur.execute("INSERT INTO users (name, domain, password, uid) VALUES ('{}', '{}', '{}', '{}') ON CONFLICT DO NOTHING;".format(user, users[user]['domain'], users[user]['password'], users[user]['uid']))

			DEBUG['started'] = True

			self.con.commit()
		return self

	def __exit__(self, _type, value, traceback):
		self.close()

	def execute(self, q, commit=True):
		log('SQLExecute: {q} [{commit}]'.format(q=q, commit=commit), level=1, product='slimIMAP', handler='postgresql')
		self.cur.execute(q)
		if commit:
			log('Commited!', level=1, product='slimIMAP', handler='postgresql')
			self.con.commit()

			#log(list(self.query('SELECT * FROM access_tokens;')), level=1)

	def query(self, q, commit=False):
		log('SQLQuery: {q} [{commit}]'.format(q=q, commit=commit), level=1, product='slimIMAP', handler='postgresql')
		self.cur.execute(q)
		if commit:
			self.con.commit()
		if self.cur.rowcount:
			for record in self.cur:
				yield wash_dict(record)

	def close(self, commit=True):
		if commit:
			self.con.commit()
		self.cur.close()
		self.con.close()

class safeDict(dict):
	def __init__(self, *args, **kwargs):
		super(safeDict, self).__init__()
		if len(args):
			for arg in args:
				if type(arg) == dict:
					for key, val in arg.items():
						self.populate(self, key, val)

		#self.update(*args, **kwargs)

	def __getitem__(self, key):
		if not key in self:
			self[key] = safeDict()
		
		val = dict.__getitem__(self, key)
		return val

	def __setitem__(self, key, val):
		dict.__setitem__(self, key, val)

	def populate(self, d, key, val):
		if type(val) == dict:
			self[key] = safeDict(val)
		#	for key, val in val.items():
		#		self.populate(self[key], key, val)
		else:
			d[key] = val

	def safe_dump(self, *args, **kwargs):
		copy = {}
		for key, val in self.items():
			if type(key) == bytes and key[0] == b'_': continue
			elif type(key) == str and key[0] == '_': continue
			elif type(val) == dict or type(val) == safeDict:
				val = val.safe_dump()
				copy[key] = val
			else:
				copy[key] = val
		return copy

def log(*args, **kwargs):
	if dCheck(config, 'log'):
		if not '_logstream' in runtime:
			runtime['_logstream'] = journal.stream('slimIMAP')

		logdata = ' '.join([str(x) for x in args])
		if dCheck(config, 'resolve'):
			## TODO: Resolve internal UID's etc to something readable
			pass

		if not 'level' in kwargs or kwargs['level'] >= config['log_level']:
			log_row = {'level' : (kwargs['level'] if 'level' in kwargs else None), 'message' : logdata}
			log_row.update(kwargs)
			print(json.dumps(log_row), file=runtime['_logstream'])