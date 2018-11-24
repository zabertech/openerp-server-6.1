Getting starting with OpenERP development
=========================================

Installation
------------

### Windows

Windows install:

:   -   executable location
    -   howto

### Debian/Ubuntu

How to get .deb packages

### Sources

In order to get the sources, you will need Bazaar version control to pull the source from Launchpad. Check how to get Bazaar according to your development environment. After having installed and configured Bazaar, setup your development environment by typing:

    mkdir source;cd source

Get the setup script of OpenERP by typing:

    bzr cat -d lp:~openerp-dev/openerp-tools/trunk setup.sh | sh

Get the current trunk version of OpenERP by typing:

    make init-trunk

The makefile contains other options. For details about options, please type:

    make

Some dependencies are necessary to use OpenERP. Depending on your environment, you might have to install the following packets:

    sudo apt-get install graphviz ghostscript postgresql python-imaging python-matplotlib 

You then have to initialise the database. This will create a new openerp role:

    make db-setup

Finally, launch the OpenERP server:

    make server

Testing your installation can be done on <http://localhost:8069/>

### Development version

Location of development version + specifics if necessary to precise

Configuration
-------------

Two configuration files are available:

-   one for the client: \~/.openerprc
-   one for the server: \~/.openerp\_serverrc

Those files follow the convention used by python's ConfigParser module.

Lines beginning with "\#" or ";" are comments.

The client configuration file is automatically generated upon the first start. The one of the server can automatically be created using the command: :

    openerp-server.py -s

If they are not found, the server and the client will start with the default configuration.

**Server Configuration File**

The server configuration file .openerp\_serverrc is used to save server startup options. Here is the list of the available options:

interface:   Address to which the server will be bound

port:   Port the server will listen on

database:   Name of the database to use

user:   Username used when connecting to the database

translate\_in:   File used to translate OpenERP to your language

translate\_out:   File used to export the language OpenERP use

language:   Use this language as the language of the server. This must be specified as an ISO country code, as specified by the W3C.

verbose:   Enable debug output

init:   init a module (use "all" for all modules)

update:   update a module (use "all" for all modules)

upgrade:   Upgrade/install/uninstall modules

db\_name:   specify the database name

db\_user:   specify the database user name

db\_password:   specify the database password

pg\_path:   specify the pg executable path

db\_host:   specify the database host

db\_port:   specify the database port

translate\_modules:   Specify modules to export. Use in combination with --i18n-export

You can create your own configuration file by specifying -s or --save on the server command line. If you would like to write an alternative configuration file, use -c &lt;config file&gt; or --config=&lt;config file&gt; Here is a basic configuration for a server:

```ini
[options]
verbose = False
xmlrpc = True
database = terp
update = {}
port = 8069
init = {}
interface = 127.0.0.1
reportgz = False
```

Full Example for Server V5.0 :

```ini
[printer]
path = none
softpath_html = none
preview = True
softpath = none

[logging]
output = stdout
logger = 
verbose = True
level = error

[help]
index = http://www.openerp.com/documentation/user-manual/
context = http://www.openerp.com/scripts/context_index.php

[form]
autosave = False
toolbar = True

[support]
recipient = support@openerp.com
support_id = 

[tip]
position = 0
autostart = False

[client]
lang = en_US
default_path = /home/user
filetype = {}
theme = none
toolbar = icons
form_tab_orientation = 0
form_tab = top

[survey]
position = 3

[path]
pixmaps = /usr/share/pixmaps/openerp-client/
share = /usr/share/openerp-client/

[login]
db = eo2
login = admin
protocol = http://
port = 8069
server = localhost
```

Command line options
--------------------

### General Options

--version show program version number and exit -h, --help show this help message and exit -c CONFIG, --config=CONFIG specify alternate config file -s, --save save configuration to \~/.terp\_serverrc -v, --verbose enable debugging --pidfile=PIDFILE file where the server pid will be stored --logfile=LOGFILE file where the server log will be stored -n INTERFACE, --interface=INTERFACE specify the TCP IP address -p PORT, --port=PORT specify the TCP port --net\_interface=NETINTERFACE specify the TCP IP address for netrpc --net\_port=NETPORT specify the TCP port for netrpc --no-netrpc disable netrpc --no-xmlrpc disable xmlrpc -i INIT, --init=INIT init a module (use "all" for all modules) --without-demo=WITHOUT\_DEMO load demo data for a module (use "all" for all modules) -u UPDATE, --update=UPDATE update a module (use "all" for all modules) --stop-after-init stop the server after it initializes --debug enable debug mode -S, --secure launch server over https instead of http --smtp=SMTP\_SERVER specify the SMTP server for sending mail

### Database related options:

-d DB\_NAME, --database=DB\_NAME  :   specify the database name

-r DB\_USER, --db\_user=DB\_USER  :   specify the database user name

-w DB\_PASSWORD, --db\_password=DB\_PASSWORD  :   specify the database password

--pg\_path=PG\_PATH specify the pg executable path --db\_host=DB\_HOST specify the database host --db\_port=DB\_PORT specify the database port

### Internationalization options:

Use these options to translate OpenERP to another language. See i18n section of the user manual. Option '-l' is mandatory.

-l LANGUAGE, --language=LANGUAGE  :   specify the language of the translation file. Use it with --i18n-export and --i18n-import

--i18n-export=TRANSLATE\_OUT  :   export all sentences to be translated to a CSV file and exit

--i18n-import=TRANSLATE\_IN  :   import a CSV file with translations and exit

--modules=TRANSLATE\_MODULES  :   specify modules to export. Use in combination with --i18n-export

### Options from previous versions:

Some options were removed in version 6. For example, `price_accuracy` is now configured through the decimal\_accuracy screen.
