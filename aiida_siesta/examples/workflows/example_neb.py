#!/usr/bin/env runaiida

#Not required by AiiDA
import os.path as op
import sys

#AiiDA classes and functions
from aiida.engine import submit
from aiida.orm import load_code
from aiida.orm import (Dict, StructureData, KpointsData)
from aiida.orm import SinglefileData

from aiida_siesta.data.psf import PsfData
from aiida_siesta.workflows.neb import NEBWorkChain

from aiida_siesta.utils.structures import clone_aiida_structure

try:
    codename = sys.argv[1]
except IndexError:
    codename = 'SiestaHere@localhost'

code = load_code(codename)

# Si8 cubic cell as host
alat = 5.430
cell = [[1.0*alat, 0.0 , 0.0,],
        [0.0, 1.0*alat , 0.0,],
        [0.0, 0.0 , 1.0*alat,],
        ]

s = StructureData(cell=cell)
s.append_atom(position=(   alat*0.000, alat*0.000, alat*0.000),symbols='Si')
s.append_atom(position=(   alat*0.500, alat*0.500, alat*0.000),symbols='Si')
s.append_atom(position=(   alat*0.500, alat*0.000, alat*0.500),symbols='Si')
s.append_atom(position=(   alat*0.000, alat*0.500, alat*0.500),symbols='Si')
s.append_atom(position=(   alat*0.250, alat*0.250, alat*0.250),symbols='Si')
s.append_atom(position=(   alat*0.750, alat*0.750, alat*0.250),symbols='Si')
s.append_atom(position=(   alat*0.750, alat*0.250, alat*0.750),symbols='Si')
s.append_atom(position=(   alat*0.250, alat*0.750, alat*0.750),symbols='Si')

host = s

# Initial: H interstitial
s_initial = clone_aiida_structure(host)
s_initial.append_atom(position=(   alat*0.000, alat*0.250, alat*0.250),symbols='H')

# Final: H interstitial in a site related by symmetry
s_final = clone_aiida_structure(host)
s_final.append_atom(position=(   alat*0.250, alat*0.250, alat*0.000),symbols='H')


# Lua script
absname = op.abspath(
        op.join(op.dirname(__file__), "../plugins/siesta/data/neb-data/neb_with_restart-new.lua"))
lua_script = SinglefileData(absname)


# Parameters: very coarse for speed of test
# Note the all the Si atoms are fixed...

parameters = dict={
   "mesh-cutoff": "50 Ry",
   "dm-tolerance": "0.001",
   "DM-NumberPulay ":  "3",
   "DM-History-Depth":  "0",
   "SCF-Mixer-weight":  "0.02",
   "SCF-Mix":   "density",
   "SCF-Mixer-kick":  "35",
   "MD-VariableCell":  "F",
   "MD-MaxCGDispl":  "0.3 Bohr",
   "MD-MaxForceTol":  " 0.04000 eV/Ang"
    }

constraints = dict={
    "%block Geometry-Constraints":
    """
    atom [ 1 -- 8 ]
    %endblock Geometry-Constraints"""
    }

relaxation = dict={
    'md-steps': 10
    }

#
# Use this for constraints
#
parameters.update(constraints)
#
neb_parameters = Dict(dict=parameters)

parameters.update(relaxation)
endpoint_parameters = Dict(dict=parameters)

    
#The basis set
basis = Dict(dict={
'pao-energy-shift': '300 meV',
'%block pao-basis-sizes': """
Si SZ
H SZ
%endblock pao-basis-sizes""",
    })


#The kpoints
kpoints_endpoints = KpointsData()
kpoints_endpoints.set_kpoints_mesh([2,2,2])

kpoints_neb = KpointsData()
kpoints_neb.set_kpoints_mesh([1,1,1])

#The pseudopotentials
pseudos_dict = {}
raw_pseudos = [("Si.psf", ['Si']), ("H.psf", ['H'])]
for fname, kinds in raw_pseudos:
    absname = op.realpath(
        op.join(op.dirname(__file__), "../plugins/siesta/data/sample-psf-family", fname))
    pseudo, created = PsfData.get_or_create(absname, use_first=True)
    if created:
        print("\nCreated the pseudo for {}".format(kinds))
    else:
        print("\nUsing the pseudo for {} from DB: {}".format(kinds, pseudo.pk))
    for j in kinds:
        pseudos_dict[j]=pseudo

#Resources
options = {
    "max_wallclock_seconds": 3600,
    'withmpi': True,
    "resources": {
        "num_machines": 1,
        "num_mpiprocs_per_machine": 2,
    }
}



inputs = {
    'initial': {
        'structure': s_initial,
        'parameters': endpoint_parameters,
        'code': code,
        'basis': basis,
        'kpoints': kpoints_endpoints,
        'pseudos': pseudos_dict,
        'options': Dict(dict=options)
    },
    'final': {
        'structure': s_final,
        'parameters': endpoint_parameters,
        'code': code,
        'basis': basis,
        'kpoints': kpoints_endpoints,
        'pseudos': pseudos_dict,
        'options': Dict(dict=options)
    },
    'neb': {
        'structure': s_initial,      # reference
        'parameters': neb_parameters,
        'code': code,
        'basis': basis,
        'kpoints': kpoints_neb,
        'pseudos': pseudos_dict,
        'lua_script': lua_script,
        'metadata': {
            "label": "H interstitial migration in Si",
            'options': options,
        }
    },
        
}

process = submit(NEBWorkChain, **inputs)
print("Submitted NEB workchain; ID={}".format(process.pk))
print(
    "For information about this workchain type: verdi process show {}".format(
        process.pk))
print("For a list of running processes type: verdi process list")
