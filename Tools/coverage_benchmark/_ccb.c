/* Minimal C callback for sys.monitoring benchmarking.
 *
 * Provides `make_recorder(disable_obj, record_set)` returning a callable
 * that optionally records its second argument into a set and returns the
 * given DISABLE sentinel (or None).  Used to isolate the cost of Python
 * function callbacks from the cost of CPython's event dispatch itself.
 *
 * Build:
 *   cc -shared -fPIC -O2 -I$SRC/Include -I$SRC $(pwd)/_ccb.c -o _ccb.so
 */
#include "Python.h"
#include <stddef.h>

typedef struct {
    PyObject_HEAD
    PyObject *retval;      /* what to return (DISABLE or None) */
    PyObject *record;      /* set to record into, or NULL */
    vectorcallfunc vectorcall;
} RecorderObject;

static PyObject *
recorder_vectorcall(PyObject *op, PyObject *const *args,
                    size_t nargsf, PyObject *kwnames)
{
    RecorderObject *self = (RecorderObject *)op;
    if (self->record != NULL) {
        Py_ssize_t nargs = PyVectorcall_NARGS(nargsf);
        if (nargs >= 2) {
            if (PySet_Add(self->record, args[1]) < 0) {
                return NULL;
            }
        }
    }
    return Py_NewRef(self->retval);
}

static void
recorder_dealloc(PyObject *op)
{
    RecorderObject *self = (RecorderObject *)op;
    Py_XDECREF(self->retval);
    Py_XDECREF(self->record);
    Py_TYPE(op)->tp_free(op);
}

static PyTypeObject Recorder_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_ccb.Recorder",
    .tp_basicsize = sizeof(RecorderObject),
    .tp_dealloc = recorder_dealloc,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_VECTORCALL,
    .tp_call = PyVectorcall_Call,
    .tp_vectorcall_offset = offsetof(RecorderObject, vectorcall),
};

static PyObject *
make_recorder(PyObject *module, PyObject *args)
{
    PyObject *retval;
    PyObject *record = Py_None;
    if (!PyArg_ParseTuple(args, "O|O", &retval, &record)) {
        return NULL;
    }
    RecorderObject *self = PyObject_New(RecorderObject, &Recorder_Type);
    if (self == NULL) {
        return NULL;
    }
    self->retval = Py_NewRef(retval);
    self->record = record == Py_None ? NULL : Py_NewRef(record);
    self->vectorcall = recorder_vectorcall;
    return (PyObject *)self;
}

static PyMethodDef methods[] = {
    {"make_recorder", make_recorder, METH_VARARGS,
     "make_recorder(retval, record_set=None) -> callable"},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT, "_ccb", NULL, 0, methods,
};

PyMODINIT_FUNC
PyInit__ccb(void)
{
    if (PyType_Ready(&Recorder_Type) < 0) {
        return NULL;
    }
    return PyModule_Create(&moduledef);
}
