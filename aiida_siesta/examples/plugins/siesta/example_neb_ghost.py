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
from aiida_siesta.utils.xyz_utils import get_structure_list_from_folder
from aiida_siesta.data.psf import PsfData

##In alternative, Data and Calculation factories could be loaded.
##They containing all the data and calculation plugins:
#from aiida.plugins import DataFactory
#from aiida.plugins import CalculationFactory
#
#SiestaCalculation = CalculationFactory('siesta.siesta')
#PsfData = DataFactory('siesta.psf')
#StructureData = DataFactory('structure')
#...

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

cell = [[15.0, 00.0 , 00.0,],
        [00.0, 15.0 , 00.0,],
        [00.0, 00.0 , 15.0,],
        ]
s = StructureData(cell=cell)
s.append_atom(position=( 0.000,  0.000,  0.000 ),symbols=['O']) #1
s.append_atom(position=( 0.757,  0.586,  0.000 ),symbols=['H']) #2
s.append_atom(position=(-0.757,  0.586,  0.000 ),symbols=['H']) #3 
s.append_atom(position=( 0.000,  3.500,  0.000 ),symbols=['O']) #4
s.append_atom(position=( 0.757,  2.914,  0.000 ),symbols=['H']) #5
s.append_atom(position=(-0.757,  2.914,  0.000 ),symbols=['H']) #6

image_structure_list = get_structure_list_from_folder("data/neb-data", s)
images = TrajectoryData(image_structure_list)

# Lua script
absname = op.abspath(
        op.join(op.dirname(__file__), "data/neb-data/neb_with_restart-new.lua"))
lua_script = SinglefileData(absname)


#The parameters
#
# NOTE that we put "by hand" an extra constraint
# on the ghost atom. Without it, the NEB algorithm
# would likely not converge, as the magnitude of the forces on
# ghosts bear no relation to the rest...
#
parameters = Dict(dict={
   "mesh-cutoff": "50 Ry",
   "dm-tolerance": "0.0001",
   "DM-NumberPulay ":  "3",
   "DM-History-Depth":  "0",
   "SCF-Mixer-weight":  "0.02",
   "SCF-Mix":   "density",
   "SCF-Mixer-kick":  "35",
   "MD-VariableCell":  "F",
   "MD-MaxCGDispl":  "0.3 Bohr",
   "MD-MaxForceTol":  " 0.04000 eV/Ang",
    "%block Geometry-Constraints":
    """
    atom [1 -- 4]
    atom 7
    %endblock Geometry-Constraints"""
    })

basis = Dict(dict={
  'floating_orbitals': [ ('O_top', 'O', (-0.757,  0.586,  2.00 ) ) ],
  '%block PAO-Basis':
    """
 O                     2                    # Species label, number of l-shells
 n=2   0   2                         # n, l, Nzeta
   3.305      2.510
   1.000      1.000
 n=2   1   2 P   1                   # n, l, Nzeta, Polarization, NzetaPol
   3.937      2.542
   1.000      1.000
H                     1                    # Species label, number of l-shells
 n=1   0   2 P   1                   # n, l, Nzeta, Polarization, NzetaPol
   4.828      3.855
   1.000      1.000

    %endblock PAO-Basis""",
})


#The kpoints
#kpoints = KpointsData()
#kpoints.set_kpoints_mesh([1, 1, 1])

#The pseudopotentials
pseudos_dict = {}
raw_pseudos = [ ("H.psf", ['H']),("O.psf", ['O', 'O_top'])]
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
    'structure': s,
    'parameters': parameters,
    'code': code,
    'basis': basis,
    'lua_script': lua_script,
    'neb_input_images': images,
    'pseudos': pseudos_dict,
    'metadata': {
        "label": "Some NEB test with H and O",
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


