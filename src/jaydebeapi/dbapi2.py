#-*- coding: utf-8 -*-

# Copyright 2010, 2011, 2012, 2013 Bastian Bowe
#
# This file is part of JayDeBeApi.
# JayDeBeApi is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# JayDeBeApi is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with JayDeBeApi.  If not, see
# <http://www.gnu.org/licenses/>.

import datetime
#import exceptions
import glob
import os
import time
import re
import sys
import warnings

_jdbc_connect = None

_java_array_byte = None

_handle_sql_exception = None

def _handle_sql_exception_jython(ex):
    from java.sql import SQLException
    if isinstance(ex, SQLException):
        raise Error
    else:
        raise ex

def _jdbc_connect_jython(jclassname, jars, libs, *args):
    if _converters is None:
        from java.sql import Types
        types = Types
        types_map = {}
        const_re = re.compile('[A-Z][A-Z_]*$')
        for i in dir(types):
            if const_re.match(i):
                types_map[i] = getattr(types, i)
        _init_converters(types_map)
    global _java_array_byte
    if _java_array_byte is None:
        import jarray
        def _java_array_byte(data):
            return jarray.array(data, 'b')
    # register driver for DriverManager
    jpackage = jclassname[:jclassname.rfind('.')]
    dclassname = jclassname[jclassname.rfind('.') + 1:]
    # print jpackage
    # print dclassname
    # print jpackage
    from java.lang import Class
    from java.lang import ClassNotFoundException
    try:
        Class.forName(jclassname).newInstance()
    except ClassNotFoundException:
        if not jars:
            raise
        _jython_set_classpath(jars)
        Class.forName(jclassname).newInstance()
    from java.sql import DriverManager
    return DriverManager.getConnection(*args)

def _jython_set_classpath(jars):
    '''
    import a jar at runtime (needed for JDBC [Class.forName])

    adapted by Bastian Bowe from
    http://stackoverflow.com/questions/3015059/jython-classpath-sys-path-and-jdbc-drivers
    '''
    from java.net import URL, URLClassLoader
    from java.lang import ClassLoader
    from java.io import File
    m = URLClassLoader.getDeclaredMethod("addURL", [URL])
    m.accessible = 1
    urls = [File(i).toURL() for i in jars]
    m.invoke(ClassLoader.getSystemClassLoader(), urls)

def _prepare_jython():
    global _jdbc_connect
    _jdbc_connect = _jdbc_connect_jython
    global _handle_sql_exception
    _handle_sql_exception = _handle_sql_exception_jython

def _handle_sql_exception_jpype(ex):
    import jpype
    SQLException = jpype.java.sql.SQLException
    if issubclass(ex.__javaclass__, SQLException):
        raise Error
    else:
        raise ex

def _jdbc_connect_jpype(jclassname, jars, libs, *driver_args):
    import jpype
    if not jpype.isJVMStarted():
        args = []
        class_path = []
        if jars:
            class_path.extend(jars)
        class_path.extend(_get_classpath())
        if class_path:
            args.append('-Djava.class.path=%s' %
                        os.path.pathsep.join(class_path))
        if libs:
            # path to shared libraries
            libs_path = os.path.pathsep.join(libs)
            args.append('-Djava.library.path=%s' % libs_path)
        # jvm_path = ('/usr/lib/jvm/java-6-openjdk'
        #             '/jre/lib/i386/client/libjvm.so')
        jvm_path = jpype.getDefaultJVMPath()
        jpype.startJVM(jvm_path, *args)
    if not jpype.isThreadAttachedToJVM():
        jpype.attachThreadToJVM()
    if _converters is None:
        types = jpype.java.sql.Types
        types_map = {}
        for i in types.__javaclass__.getClassFields():
            types_map[i.getName()] = i.getStaticAttribute()
        _init_converters(types_map)
    global _java_array_byte
    if _java_array_byte is None:
        def _java_array_byte(data):
            return jpype.JArray(jpype.JByte, 1)(data)
    # register driver for DriverManager
    jpype.JClass(jclassname)
    return jpype.java.sql.DriverManager.getConnection(*driver_args)

def _get_classpath():
    """Extract CLASSPATH from system environment as JPype doesn't seem
    to respect that variable.
    """
    try:
        orig_cp = os.environ['CLASSPATH']
    except KeyError:
        return []
    expanded_cp = []
    for i in orig_cp.split(os.path.pathsep):
        expanded_cp.extend(_jar_glob(i))
    return expanded_cp

def _jar_glob(item):
    if item.endswith('*'):
        return glob.glob('%s.[jJ][aA][rR]' % item)
    else:
        return [item]

def _prepare_jpype():
    global _jdbc_connect
    _jdbc_connect = _jdbc_connect_jpype
    global _handle_sql_exception
    _handle_sql_exception = _handle_sql_exception_jpype

if sys.platform.lower().startswith('java'):
    _prepare_jython()
else:
    _prepare_jpype()

apilevel = '2.0'
threadsafety = 1
paramstyle = 'qmark'

class DBAPITypeObject(object):
    _mappings = {}
    def __init__(self,*values):
        self.values = values
        for i in values:
            if i in DBAPITypeObject._mappings:
                raise ValueError("Non unique mapping for type '%s'" % i)
            DBAPITypeObject._mappings[i] = self
    def __cmp__(self,other):
        if other in self.values:
            return 0
        if other < self.values:
            return 1
        else:
            return -1
    @classmethod
    def _map_jdbc_type_to_dbapi(cls, jdbc_type):
        try:
            return cls._mappings[jdbc_type.upper()]
        except KeyError:
            warnings.warn("No type mapping for JDBC type '%s'. "
                          "Using None as a default." % jdbc_type)
            return None


STRING = DBAPITypeObject("CHARACTER", "CHAR", "VARCHAR",
                          "CHARACTER VARYING", "CHAR VARYING", "STRING",)

TEXT = DBAPITypeObject("CLOB", "CHARACTER LARGE OBJECT",
                       "CHAR LARGE OBJECT",  "XML",)

BINARY = DBAPITypeObject("BLOB", "BINARY LARGE OBJECT",)

NUMBER = DBAPITypeObject("INTEGER", "INT", "SMALLINT", "BIGINT",)

FLOAT = DBAPITypeObject("FLOAT", "REAL", "DOUBLE", "DECFLOAT")

DECIMAL = DBAPITypeObject("DECIMAL", "DEC", "NUMERIC", "NUM",)

DATE = DBAPITypeObject("DATE",)

TIME = DBAPITypeObject("TIME",)

DATETIME = DBAPITypeObject("TIMESTAMP",)

ROWID = DBAPITypeObject(())

# DB-API 2.0 Module Interface Exceptions
class Error(Exception):
    pass

class Warning(Exception):
    pass

class InterfaceError(Error):
    pass

class DatabaseError(Error):
    pass

class InternalError(DatabaseError):
    pass

class OperationalError(DatabaseError):
    pass

class ProgrammingError(DatabaseError):
    pass

class IntegrityError(DatabaseError):
    pass

class DataError(DatabaseError):
    pass

class NotSupportedError(DatabaseError):
    pass

# DB-API 2.0 Type Objects and Constructors

def _java_sql_blob(data):
    return _java_array_byte(data)

Binary = _java_sql_blob

def _str_func(func):
    def to_str(*parms):
        return str(func(*parms))
    return to_str

Date = _str_func(datetime.date)

Time = _str_func(datetime.time)

Timestamp = _str_func(datetime.datetime)

def DateFromTicks(ticks):
    return Date(*time.localtime(ticks)[:3])

def TimeFromTicks(ticks):
    return Time(*time.localtime(ticks)[3:6])

def TimestampFromTicks(ticks):
    return Timestamp(*time.localtime(ticks)[:6])

# DB-API 2.0 Module Interface connect constructor
def connect(jclassname, driver_args, jars=None, libs=None):
    """Open a connection to a database using a JDBC driver and return
    a Connection instance.

    jclassname: Full qualified Java class name of the JDBC driver.
    driver_args: Argument or sequence of arguments to be passed to the
           Java DriverManager.getConnection method. Usually the
           database URL. See
           http://docs.oracle.com/javase/6/docs/api/java/sql/DriverManager.html
           for more details
    jars: Jar filename or sequence of filenames for the JDBC driver
    libs: Dll/so filenames or sequence of dlls/sos used as shared
          library by the JDBC driver
    """
    if isinstance(driver_args, str):
        driver_args = [ driver_args ]
    if jars:
        if isinstance(jars, str):
            jars = [ jars ]
    else:
        jars = []
    if libs:
        if isinstance(libs, str):
            libs = [ libs ]
    else:
        libs = []
    jconn = _jdbc_connect(jclassname, jars, libs, *driver_args)
    return Connection(jconn, _converters)

# DB-API 2.0 Connection Object
class Connection(object):

    Error = Error
    Warning = Warning
    InterfaceError = InterfaceError
    DatabaseError = DatabaseError
    InternalError = InternalError
    OperationalError = OperationalError
    ProgrammingError = ProgrammingError
    IntegrityError = IntegrityError
    DataError = DataError
    NotSupportedError = NotSupportedError

    def __init__(self, jconn, converters):
        self.jconn = jconn
        self._closed = False
        self._converters = converters

    def close(self):
        if self._closed:
            raise Error
        self.jconn.close()
        self._closed = True

    def commit(self):
        try:
            self.jconn.commit()
        except Exception as ex:
            _handle_sql_exception(ex)

    def rollback(self):
        try:
            self.jconn.rollback()
        except Exception as ex:
            _handle_sql_exception(ex)

    def cursor(self):
        return Cursor(self, self._converters)

# DB-API 2.0 Cursor Object
class Cursor(object):

    rowcount = -1
    _meta = None
    _prep = None
    _rs = None
    _description = None

    def __init__(self, connection, converters):
        self._connection = connection
        self._converters = converters

    @property
    def description(self):
        if self._description:
            return self._description
        m = self._meta
        if m:
            count = m.getColumnCount()
            self._description = []
            for col in range(1, count + 1):
                size = m.getColumnDisplaySize(col)
                jdbc_type = m.getColumnTypeName(col)
                dbapi_type = DBAPITypeObject._map_jdbc_type_to_dbapi(jdbc_type)
                col_desc = ( m.getColumnName(col),
                             dbapi_type,
                             size,
                             size,
                             m.getPrecision(col),
                             m.getScale(col),
                             m.isNullable(col),
                             )
                self._description.append(col_desc)
            return self._description

#   optional callproc(self, procname, *parameters) unsupported

    def close(self):
        self._close_last()
        self._connection = None

    def _close_last(self):
        """Close the resultset and reset collected meta data.
        """
        if self._rs:
            self._rs.close()
        self._rs = None
        if self._prep:
            self._prep.close()
        self._prep = None
        self._meta = None
        self._description = None

    # TODO: this is a possible way to close the open result sets
    # but I'm not sure when __del__ will be called
    __del__ = _close_last

    def _set_stmt_parms(self, prep_stmt, parameters):
        for i in range(len(parameters)):
            # print (i, parameters[i], type(parameters[i]))
            prep_stmt.setObject(i + 1, parameters[i])

    def execute(self, operation, parameters=None):
        if self._connection._closed:
            raise Error
        if not parameters:
            parameters = ()
        self._close_last()
        self._prep = self._connection.jconn.prepareStatement(operation)
        self._set_stmt_parms(self._prep, parameters)
        try:
            is_rs = self._prep.execute()
        except Exception as ex:
            _handle_sql_exception(ex)
        if is_rs:
            self._rs = self._prep.getResultSet()
            self._meta = self._rs.getMetaData()
            self.rowcount = -1
        else:
            self.rowcount = self._prep.getUpdateCount()
        # self._prep.getWarnings() ???

    def executemany(self, operation, seq_of_parameters):
        self._close_last()
        self._prep = self._connection.jconn.prepareStatement(operation)
        for parameters in seq_of_parameters:
            self._set_stmt_parms(self._prep, parameters)
            self._prep.addBatch()
        update_counts = self._prep.executeBatch()
        # self._prep.getWarnings() ???
        self.rowcount = sum(update_counts)
        self._close_last()

    def fetchone(self):
        if not self._rs:
            raise Error
        if not self._rs.next():
            return None
        row = []
        for col in range(1, self._meta.getColumnCount() + 1):
            sqltype = self._meta.getColumnType(col)
            # print sqltype
            # TODO: Oracle 11 will read a oracle.sql.TIMESTAMP
            # which can't be converted to string easily
            v = self._rs.getObject(col)
            if v:
                converter = self._converters.get(sqltype)
                if converter:
                    v = converter(v)
            row.append(v)
        return tuple(row)

    def fetchmany(self, size=None):
        if not self._rs:
            raise Error
        if size is None:
            size = self.arraysize
        # TODO: handle SQLException if not supported by db
        self._rs.setFetchSize(size)
        rows = []
        row = None
        for i in range(size):
            row = self.fetchone()
            if row is None:
                break
            else:
                rows.append(row)
        # reset fetch size
        if row:
            # TODO: handle SQLException if not supported by db
            self._rs.setFetchSize(0)
        return rows

    def fetchall(self):
        rows = []
        while True:
            row = self.fetchone()
            if row is None:
                break
            else:
                rows.append(row)
        return rows

    # optional nextset() unsupported

    arraysize = 1

    def setinputsizes(self, sizes):
        pass

    def setoutputsize(self, size, column=None):
        pass

def _to_datetime(java_val):
    d = datetime.datetime.strptime(str(java_val)[:19], "%Y-%m-%d %H:%M:%S")
    if not isinstance(java_val, str):
        d = d.replace(microsecond=int(str(java_val.getNanos())[:6]))
    return d
    # return str(d)
    # return str(java_val)

def _to_date(java_val):
    d = datetime.datetime.strptime(str(java_val)[:10], "%Y-%m-%d").date()
    return d
    # return d.strftime("%Y-%m-%d")
    # return str(java_val)

def _java_to_py(java_method):
    def to_py(java_val):
        if isinstance(java_val, (str, int, float, bool)):
            return java_val
        return getattr(java_val, java_method)()
    return to_py

_to_double = _java_to_py('doubleValue')

_to_int = _java_to_py('intValue')

_to_long = _java_to_py('longValue')

def _init_converters(types_map):
    """Prepares the converters for conversion of java types to python
    objects.
    types_map: Mapping of java.sql.Types field name to java.sql.Types
    field constant value"""
    global _converters
    _converters = {}
    for i in _DEFAULT_CONVERTERS:
        const_val = types_map[i]
        _converters[const_val] = _DEFAULT_CONVERTERS[i]

# Mapping from java.sql.Types field to converter method
_converters = None

_DEFAULT_CONVERTERS = {
    # see
    # http://download.oracle.com/javase/1.4.2/docs/api/java/sql/Types.html
    # for possible keys
    'TIMESTAMP': _to_datetime,
    'DATE': _to_date,
    'BINARY': str,
    'DECIMAL': _to_double,
    'NUMERIC': _to_double,
    'DOUBLE': _to_double,
    'FLOAT': _to_double,
    'INTEGER': _to_int,
    'BIGINT': _to_long,
    'TINYINT': _to_int,
    'SMALLINT': _to_int,
    'BOOLEAN': _java_to_py('booleanValue'),
}
