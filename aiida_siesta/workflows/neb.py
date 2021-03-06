from aiida import orm
from aiida.engine import WorkChain, calcfunction, ToContext
from aiida.common import AttributeDict
from aiida_siesta.workflows.base import SiestaBaseWorkChain
from aiida_siesta.workflows.neb_base import SiestaBaseNEBWorkChain
from aiida_siesta.calculations.tkdict import FDFDict
from aiida_siesta.utils.interpol import interpolate_two_structures_ase


class NEBWorkChain(WorkChain):

    """
    Workchain to run a NEB MEP optimization
    starting from two end-point structures
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.expose_inputs(SiestaBaseWorkChain, exclude=('structure',), namespace="initial")
        spec.expose_inputs(SiestaBaseWorkChain, exclude=('structure',), namespace="final")
        spec.expose_inputs(SiestaBaseNEBWorkChain, exclude=('starting_path',), namespace="neb")

        spec.input('initial_structure', valid_type=orm.StructureData,
                   help='Initial Structure in Path')
        spec.input('final_structure', valid_type=orm.StructureData,
                   help='Final Structure in Path')
        spec.input('n_images', valid_type=orm.Int,
                   help='Number of (internal) images  in Path')

        # Note: in this version, n_images must be compatible
        # with the Lua script settings.. 
        
        spec.output('neb_output_package', valid_type=orm.TrajectoryData)

        spec.outline(

            cls.relax_initial,
            cls.relax_final,
            cls.generate_starting_path,
            cls.run_neb,
            cls.run_results,
        )
        spec.exit_code(200, 'ERROR_MAIN_WC', message='The end-point relaxation SiestaBaseWorkChain failed')
        spec.exit_code(201, 'ERROR_FINAL_WC', message='The NEB calculation failed')

    def relax_initial(self):
        """
        Run the SiestaBaseWorkChain, might be a relaxation or a scf only.
        """

        inputs = self.exposed_inputs(SiestaBaseWorkChain,
                                     namespace='initial')
        inputs['structure'] = self.inputs.initial_structure

        running = self.submit(SiestaBaseWorkChain, **inputs)
        self.report(f'Launched SiestaBaseWorkChain<{running.pk}> to relax the initial structure.')

        return ToContext(initial_relaxation_wk=running)

    def relax_final(self):
        """
        Run the SiestaBaseWorkChain, might be a relaxation or a scf only.
        """

        inputs = self.exposed_inputs(SiestaBaseWorkChain,
                                     namespace='final')
        inputs['structure'] = self.inputs.final_structure

        running = self.submit(SiestaBaseWorkChain, **inputs)
        self.report(f'Launched SiestaBaseWorkChain<{running.pk}> to relax the final structure.')

        return ToContext(final_relaxation_wk=running)

    def generate_starting_path(self):

        initial_wk =  self.ctx.initial_relaxation_wk 
        if not initial_wk.is_finished_ok:
            return self.exit_codes.ERROR_MAIN_WC

        final_wk =  self.ctx.final_relaxation_wk 
        if not final_wk.is_finished_ok:
            return self.exit_codes.ERROR_MAIN_WC
        
        s_initial = initial_wk.outputs.output_structure
        s_final = final_wk.outputs.output_structure

        n_images = self.inputs.n_images.value
        images_list = interpolate_two_structures_ase(s_initial,
                                                     s_final,
                                                     n_images)
        path_object = orm.TrajectoryData(images_list)
        #
        # Use a 'serializable' dictionary instead of the 
        # actual kinds list
        #
        _kinds_raw = [ k.get_raw() for k in s_initial.kinds ]
        path_object.set_attribute('kinds', _kinds_raw)
        
        self.ctx.path = path_object

        self.report(f'Generated starting path for NEB.')
        
        
    def run_neb(self):
        """
        .
        """
        inputs = self.exposed_inputs(SiestaBaseNEBWorkChain, namespace='neb')

        print(inputs)
        
        inputs['starting_path'] = self.ctx.path

        running = self.submit(SiestaBaseNEBWorkChain, **inputs)

        self.report(f'Launched SiestaBaseNEBWorkChain<{running.pk}> for NEB.')

        return ToContext(neb_wk=running)

    def run_results(self):

        if not self.ctx.neb_wk.is_finished_ok:
                return self.exit_codes.ERROR_FINAL_WC
        else:
            outps = self.ctx.neb_wk.outputs

        neb_output = outps['neb_output_package']
        n_iterations = neb_output.get_attribute('neb_iterations')
        
        self.out('neb_output_package', neb_output)
        self.report(f'NEB process done in {n_iterations} iterations.')


#    @classmethod
#    def inputs_generator(cls):  # pylint: disable=no-self-argument,no-self-use
#        from aiida_siesta.utils.inputs_generators import BaseWorkChainInputsGenerator
#        return BaseWorkChainInputsGenerator(cls)
