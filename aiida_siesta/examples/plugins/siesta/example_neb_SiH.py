#!/usr/bin/env runaiida

#Not required by AiiDA
import os.path as op
import sys

#AiiDA classes and functions
from aiida.engine import submit
from aiida.orm import load_code
from aiida.orm import (Dict, StructureData, KpointsData)
from aiida.orm import TrajectoryData, SinglefileData
from aiida_siesta.calculations.siesta import SiestaCalculation
from aiida_siesta.utils.interpol import interpolate_two_structures_ase
from aiida_siesta.utils.structures import clone_aiida_structure


from aiida_siesta.data.psf import PsfData

try:
    dontsend = sys.argv[1]
    if dontsend == "--dont-send":
        submit_test = True
    elif dontsend == "--send":
        submit_test = False
    else:
        raise IndexError
except IndexError:
    print(("The first parameter can only be either "
           "--send or --dont-send"),
          file=sys.stderr)
    sys.exit(1)

try:
    codename = sys.argv[2]
except IndexError:
    codename = 'Siesta4.0.1@kelvin'

#The code
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

image_structure_list = interpolate_two_structures_ase(s_initial, s_final, n_images=5)
images = TrajectoryData(image_structure_list)

# Lua script
absname = op.abspath(
        op.join(op.dirname(__file__), "data/neb-data/neb_with_restart-new.lua"))
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

#
# Use this for constraints
#
parameters.update(constraints)
#
parameters = Dict(dict=parameters)

    
#The basis set
basis = Dict(dict={
'pao-energy-shift': '300 meV',
'%block pao-basis-sizes': """
Si SZ
H SZ
%endblock pao-basis-sizes""",
    })


#The kpoints
#kpoints = KpointsData()
#kpoints.set_kpoints_mesh([2, 2, 2])

#The pseudopotentials
pseudos_dict = {}
raw_pseudos = [("Si.psf", ['Si']), ("H.psf", ['H'])]
for fname, kinds in raw_pseudos:
    absname = op.realpath(
        op.join(op.dirname(__file__), "data/sample-psf-family", fname))
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


#The submission
#All the inputs of a Siesta calculations are listed in a dictionary
inputs = {
    'structure': s_initial,
    'parameters': parameters,
    'code': code,
    'basis': basis,
    'lua_script': lua_script,
#    'kpoints': kpoints,
    'neb_input_images': images,
    'pseudos': pseudos_dict,
    'metadata': {
        "label": "H interstitial migration in Si",
        'options': options,
    }
}

if submit_test:
    inputs["metadata"]["dry_run"] = True
    inputs["metadata"]["store_provenance"] = False
    process = submit(SiestaCalculation, **inputs)
    print("Submited test for calculation (uuid='{}')".format(process.uuid))
    print("Check the folder submit_test for the result of the test")

else:
    process = submit(SiestaCalculation, **inputs)
    print("Submitted calculation; ID={}".format(process.pk))
    print("For information about this calculation type: verdi process show {}".
          format(process.pk))
    print("For a list of running processes type: verdi process list")

##An alternative is be to use the builder
#build=SiestaCalculation.get_builder()
#build.code=code
#build.structure=structure
#build.pseudos=pseudos_dict
#...
#build.metadata.options.resources = {'num_machines': 1 "num_mpiprocs_per_machine": 1}
#process = submit(builder)

