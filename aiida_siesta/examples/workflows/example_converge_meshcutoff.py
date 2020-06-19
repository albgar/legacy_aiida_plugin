#!/usr/bin/env runaiida

'''
This is an example of how to converge a parameter using the aiida_siesta
plugin.

More specifically, we will converge the mesh cutoff here, but you can do the
same for other parameters/basis parameters/attributes...
'''

#Not required by AiiDA
import os.path as op
import sys

#AiiDA classes and functions
from aiida.engine import submit
from aiida.orm import load_code
from aiida.orm import Float, Dict, StructureData, KpointsData
from aiida_siesta.data.psf import PsfData
from aiida_siesta.workflows.iterate import SiestaConverger

'''
First of all, we need to setup all the inputs of the calculations.

See https://aiida-siesta-plugin.readthedocs.io/en/stable/workflows/base.html#inputs.

Basically, we will build an "inputs" dict at the end of the file, and all we are doing until
there is to build every part of it step by step.

All this is general to any SIESTA calculation with AiiDa, so if you already know how it works,
go to the end of the file, where we really do the iterate specific stuff.
'''

# Load the version of siesta that we are going to use
try:
    codename = sys.argv[1]
except IndexError:
    codename = 'Siesta-4.0.2@kay'
code = load_code(codename)

# Generate the structure (or get it from somewhere else)
try:
    # We can get it using sisl (useful if we have it in an *fdf, *XV, ...)
    import sisl
    
    ase_struct = sisl.geom.diamond(5.430, 'Si').toASE()
except:
    # Or using ASE
    import ase

    ase_struct = ase.build.bulk('Si', 'diamond', 5.430)
# Then just pass it to StructureData, which is the type that Aiida works with
structure = StructureData(ase=ase_struct)

# Specify some parameters that go into the fdf file
parameters = Dict(
    dict={
        'xc-functional': 'LDA',
        'xc-authors': 'CA',
        'max-scfiterations': 40,
        'dm-numberpulay': 4,
        'dm-mixingweight': 0.3,
        'dm-tolerance': 1.e-5,
        'Solution-method': 'diagon',
        'electronic-temperature': '25 meV',
    })

# Extra parameters that also go to the fdf file, but are related
# to the basis.
basis = Dict(
    dict={
        'pao-energy-shift': '300 meV',
        '%block pao-basis-sizes': """
Si DZP
%endblock pao-basis-sizes""",
    })

# Define the kpoints for the simulations. Note that this is not passed as
# a normal fdf parameter, it has "its own input"
kpoints = KpointsData()
kpoints.set_kpoints_mesh([14, 14, 14])

# Get the appropiate pseudos (in "real life", one could have a pseudos family defined
# in aiida database with `verdi data psf uploadfamily <path to folder> <family name>`)
# and then pass it as a simple string, Aiida will know which pseudos to use.
# See the pseudo_family in the aiida_siesta docs (link on top of the file)
pseudos_dict = {}
raw_pseudos = [("Si.psf", ['Si'])]
for fname, kinds in raw_pseudos:
    absname = op.realpath(
        op.join(op.dirname(__file__),
                "../plugins/siesta/data/sample-psf-family", fname))
    pseudo, created = PsfData.get_or_create(absname, use_first=True)
    if created:
        print("\nCreated the pseudo for {}".format(kinds))
    else:
        print("\nUsing the pseudo for {} from DB: {}".format(kinds, pseudo.pk))
    for j in kinds:
        pseudos_dict[j] = pseudo

# Options that are related to how the job is technically submitted and
# run. Some of this options define flags for the job manager (e.g. SLURM)
# and some other's are related to how the code is executed. Note that 
# 'max_wallclock_seconds' is a required option, so that SIESTA can stop
# gracefully before the job runs out of time.
options = Dict(
    dict={
        "max_wallclock_seconds": 360,
        #'withmpi': True,
        #'account': "tcphy113c",
        #'queue_name': "DevQ",
        "resources": {
            "num_machines": 1,
            "num_mpiprocs_per_machine": 1,
        }
    })

# Now we have all inputs defined, so as promised at the beggining of the file
# we build the inputs dicts to pass it to the process. There's no need though,
# we could pass each input separately. This is just so that the process call
# looks cleaner.
inputs = {
    'structure': structure,
    'parameters': parameters,
    'code': code,
    'basis': basis,
    'kpoints': kpoints,
    'pseudos': pseudos_dict,
    'options': options,
}

# Up until this point, all the things done have been general to any SIESTA
# simulation. Now, we will use the SiestaConverger to converge the mesh cutoff.

# Iterate over meshcutoff
process = submit(SiestaConverger, **inputs,
    iterate_over={
        'meshcutoff': [100,200,300,400,500,600,700,800,900],
    },
    batch_size=Int(4)
)

# Print some info
print("Submitted workchain; ID={}".format(process.pk))
print(
    "For information about this workchain type: verdi process show {}".format(
        process.pk))
print("For a list of running processes type: verdi process list")