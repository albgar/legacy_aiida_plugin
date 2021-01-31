from aiida import orm
from aiida.engine import WorkChain, calcfunction, ToContext
from aiida.common import AttributeDict
from aiida_siesta.workflows.base import SiestaBaseWorkChain
from aiida_siesta.calculations.siesta import SiestaCalculation
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
        spec.expose_inputs(SiestaBaseWorkChain, namespace="initial")
        spec.expose_inputs(SiestaBaseWorkChain, namespace="final")
        spec.expose_inputs(SiestaCalculation, namespace="neb")
        
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

        inputs = self.inputs.initial

        running = self.submit(SiestaBaseWorkChain, **inputs)
        self.report(f'Launched SiestaBaseWorkChain<{running.pk}> to relax the initial structure.')

        return ToContext(initial_relaxation_wk=running)

    def relax_final(self):
        """
        Run the SiestaBaseWorkChain, might be a relaxation or a scf only.
        """

        inputs = self.inputs.final

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

        images_list = interpolate_two_structures_ase(s_initial,
                                                     s_final,
                                                     5)
        self.ctx.input_images = orm.TrajectoryData(images_list)
        
    def run_neb(self):
        """
        .
        """
        inputs = self.exposed_inputs(SiestaCalculation, namespace='neb')
#        inputs['neb_input_images'] = self.ctx.input_images

        running = self.submit(SiestaCalculation, neb_input_images=self.ctx.input_images, **inputs)
        #running = self.submit(SiestaCalculation, **inputs)
        self.report(f'Launched SiestaCalculation<{running.pk}> for NEB.')

        return ToContext(neb_wk=running)

    def run_results(self):

        if not self.ctx.neb_wk.is_finished_ok:
                return self.exit_codes.ERROR_FINAL_WC
        else:
            outps = self.ctx.neb_wk.outputs

        self.out('neb_output_package', outps['neb_output_images'])


#    @classmethod
#    def inputs_generator(cls):  # pylint: disable=no-self-argument,no-self-use
#        from aiida_siesta.utils.inputs_generators import BaseWorkChainInputsGenerator
#        return BaseWorkChainInputsGenerator(cls)
