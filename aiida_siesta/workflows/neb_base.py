from aiida import orm
from aiida.engine import WorkChain, calcfunction, ToContext
from aiida_siesta.calculations.siesta import SiestaCalculation
from aiida.orm.nodes.data.structure import Kind

class SiestaBaseNEBWorkChain(WorkChain):

    """
    Workchain to run a NEB MEP optimization
    starting from a guessed path
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.expose_inputs(SiestaCalculation,
                           exclude=('structure','lua_script',
                                    'neb_input_images','metadata'))

        # We might enforce the kinds annotation by using a new data type,
        # but it would be wasteful
        spec.input('starting_path', valid_type=orm.TrajectoryData,
                   help='Starting Path')
        spec.input('neb_script', valid_type=orm.SinglefileData,
                   help='Lua script for NEB engine')

        spec.input('options', valid_type=orm.Dict, help='Options')

        # These to be implemented by a config.lua file passed to the calculation
        # For consistency checks we  might need some extra metadata in the Lua object
        
        # spec.input('spring_constant', valid_type=orm.Float, required=False)
        # spec.input('climbing_image', valid_type=orm.Bool, required=False)
        # spec.input('max_number_of_neb_iterations', valid_type=orm.Int, required=False)
        # ... tolerances, etc are encoded in the Siesta params dictionary.
        
        # Note: in this version, n_images must be compatible
        # with the Lua script settings.. 
        
        spec.output('neb_output_package', valid_type=orm.TrajectoryData)

        spec.outline(

            cls.check_input_path,
            cls.run_neb,
            cls.run_results,
        )
        spec.exit_code(201, 'ERROR_PATH_SPEC', message='The path specification is faulty')
        spec.exit_code(201, 'ERROR_NEB_CALC', message='The NEB calculation failed')

    def check_input_path(self):
        """
        Make sure that the input set of images is consistent, and is annotated with
        the kinds of the structure
        """
        path = self.inputs.starting_path

        if path.numsteps == 0:
            self.report('The trajectory data object does not contain any structures')
            return self.exit_codes.ERROR_PATH_SPEC

        if path.numsteps == 1:
            self.report('The trajectory data object does not represent a path')
            return self.exit_codes.ERROR_PATH_SPEC
            
        if path.numsteps == 2:
            self.report('The trajectory data object contains only two structures...')
            # We could just interpolate, but here this is an error
            return self.exit_codes.ERROR_PATH_SPEC

        # ... further "smoothness" tests could be implemented if needed
        
        try:
            _kinds_raw = path.get_attribute('kinds')
        except AttributeError:
            self.report('No kinds attribute found in TrajectoryData object')
            return self.exit_codes.ERROR_PATH_SPEC

        # Create proper kinds list from list of raw dictionaries
        _kinds = [ Kind(raw=kr) for kr in _kinds_raw]
        
        ref_structure = path.get_step_structure(0,custom_kinds=_kinds)
        
        self.ctx.reference_structure = ref_structure
        
    def run_neb(self):
        """
        Run a SiestaCalculation with a specific NEB images
        input.
        """
        
        inputs = self.exposed_inputs(SiestaCalculation)

        inputs['neb_input_images'] = self.inputs.starting_path
        inputs['lua_script'] = self.inputs.neb_script
        inputs['structure'] = self.ctx.reference_structure

        #
        # Note this
        #
        inputs['metadata'] = {
            "label": "NEB calculation",
            'options': self.inputs.options.get_dict(),
         }

        running = self.submit(SiestaCalculation, **inputs)
        self.report(f'Launched SiestaCalculation<{running.pk}> for NEB.')

        return ToContext(neb_wk=running)

    def run_results(self):

        if not self.ctx.neb_wk.is_finished_ok:
                return self.exit_codes.ERROR_NEB_CALC
        else:
            outps = self.ctx.neb_wk.outputs

        # We might also take the 'retrieved' folder and parse the NEB data here
        #
        neb_output = outps['neb_output_images']
        n_iterations = neb_output.get_attribute('neb_iterations')
        
        self.out('neb_output_package', neb_output)
        self.report(f'NEB process done in {n_iterations} iterations.')


#    @classmethod
#    def inputs_generator(cls):  # pylint: disable=no-self-argument,no-self-use
#        from aiida_siesta.utils.inputs_generators import BaseWorkChainInputsGenerator
#        return BaseWorkChainInputsGenerator(cls)
