#FF5
# main.py options:

# debug                          = False
## debug - debug mode
# detector                       = ''
## detector - Detector to use if client fails to provide normalized face
## (nnd).Use "nnd" if you need to detect faces in such requests. Empty value
## rejects requests without normalized.
host                           = '0.0.0.0'
## host - host to listen
port                           = 18820
## port - port to listen
# prometheus_timing_buckets      = None
## prometheus_timing_buckets - prometheus histogram buckets (python list of
## numbers, e.g. [1,2,3])
sfapi_url                      = 'http://127.0.0.1:18411'
## sfapi_url - SF-API URL
# version                        = False
## version - print version

# plugin_dir.py options:

plugin_dir                     = '/etc/unlift_plugins/'
## plugin_dir - Plugin directory for plugin_source='dir'

# abstract_define.py options:

plugin_source                  = 'dir'
## plugin_source - Plugin source (dir)

# log.py options:

# log_file_max_size              = 100000000
## log_file_max_size - max size of log files before rollover
# log_file_num_backups           = 10
## log_file_num_backups - number of log files to keep
# log_file_prefix                = None
## log_file_prefix - Path prefix for log files. Note that if you are running
## multiple tornado processes, log_file_prefix must be different for each of
## them (e.g. include the port number)
# log_rotate_interval            = 1
## log_rotate_interval - The interval value of timed rotating
# log_rotate_mode                = 'size'
## log_rotate_mode - The mode of rotating files(time or size)
# log_rotate_when                = 'midnight'
## log_rotate_when - specify the type of TimedRotatingFileHandler interval other
## options:('S', 'M', 'H', 'D', 'W0'-'W6')
# log_to_stderr                  = None
## log_to_stderr - Send log output to stderr (colorized if possible). By default
## use stderr if --log_file_prefix is not set and no other logging is
## configured.
# logging                        = 'info'
## logging - Set the Python log level. If 'none', tornado won't touch the
## logging configuration.