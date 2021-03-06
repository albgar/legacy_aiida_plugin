from aiida import orm
from aiida.engine import WorkChain, ToContext
from aiida_siesta.workflows.neb_base import SiestaBaseNEBWorkChain
from aiida_siesta.workflows.base import SiestaBaseWorkChain
from aiida_siesta.utils.structures import clone_aiida_structure
from aiida_siesta.utils.interpol import interpolate_two_structures_ase

class InterstitialBarrierWorkChain(WorkChain):

    """
    Workchain to compute the barrier for interstitial
    diffusion starting from the host structure and
    initial and final interstitial positions
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.expose_inputs(SiestaBaseWorkChain,
                           exclude=('structure',),
                           namespace="initial")
        spec.expose_inputs(SiestaBaseWorkChain,
                           exclude=('structure',),
                           namespace="final")

        spec.expose_inputs(SiestaBaseNEBWorkChain,
                           exclude=('starting_path',),
                           namespace="neb")

        spec.input('host_structure', valid_type=orm.StructureData,
                   help='Host structure')
        spec.input('interstitial_symbol', valid_type=orm.Str,
                   help='Chemical symbol of interstitial species')
        #
        # These should be lists of floats. Pending validations
        #
        spec.input('initial_position', valid_type=orm.List,  # validator...
                   help='Initial position of interstitial in host structure')
        spec.input('final_position', valid_type=orm.List,    # validator...
                   help='Final position of interstitial in host structure')

        spec.input('n_images', valid_type=orm.Int,
                   help='Number of (internal) images  in Path')

        spec.expose_outputs(SiestaBaseNEBWorkChain)

        spec.outline(

            cls.prepare_structures,
            cls.relax_initial,
            cls.relax_final,
            cls.prepare_initial_path,
            cls.run_NEB_workchain,
            cls.check_results
        )
        spec.exit_code(200, 'ERROR_MAIN_WC', message='The end-point relaxation SiestaBaseWorkChain failed')
        spec.exit_code(250, 'ERROR_CONFIG', message='Cannot figure out interstitial position(s)')
        spec.exit_code(300, 'ERROR_NEB_WK', message='NEBWorkChain did not finish correctly')

    def prepare_structures(self):
        """
        Make copies of host structure and add interstitials
        """

        host = self.inputs.host_structure
        initial_position = self.inputs.initial_position.get_list()
        final_position = self.inputs.final_position.get_list()
        atom_symbol = self.inputs.interstitial_symbol.value

        # With pseudo families and smart fallback to chemical symbol,
        # the addition of '_int' to the interstitial atom is easily supported
        # If not, the pseudo must be manually included.
        #
        s_initial = clone_aiida_structure(host)
        s_final   = clone_aiida_structure(host)

        try:
            s_initial.append_atom(symbols=atom_symbol,
                                  position=initial_position,
                                  name=atom_symbol+ '_int')

            s_final.append_atom(symbols=atom_symbol,
                                position=final_position,
                                name=atom_symbol+ '_int')
        except:
            self.report("Problem adding atom to end-points")
            return self.exit_codes.ERROR_CONFIG

        self.ctx.s_initial = s_initial
        self.ctx.s_final = s_final
        self.ctx.atom_symbol = atom_symbol

        self.report(f'Created initial and final structures')

    def relax_initial(self):
        """
        Run the SiestaBaseWorkChain, might be a relaxation or a scf only.
        """

        inputs = self.exposed_inputs(SiestaBaseWorkChain,
                                     namespace='initial')
        inputs['structure'] = self.ctx.s_initial

        running = self.submit(SiestaBaseWorkChain, **inputs)
        self.report(f'Launched SiestaBaseWorkChain<{running.pk}> to relax the initial structure.')

        return ToContext(initial_relaxation_wk=running)

    def relax_final(self):
        """
        Run the SiestaBaseWorkChain, might be a relaxation or a scf only.
        """

        inputs = self.exposed_inputs(SiestaBaseWorkChain,
                                     namespace='final')
        inputs['structure'] = self.ctx.s_final

        running = self.submit(SiestaBaseWorkChain, **inputs)
        self.report(f'Launched SiestaBaseWorkChain<{running.pk}> to relax the final structure.')

        return ToContext(final_relaxation_wk=running)


    def prepare_initial_path(self):
        """
        Nothing special to do for the interstitial case. If needed, a subclass might implement
        special heuristics to avoid bad guesses for specific cases.
        Here we just interpolate.
        """
        
        initial_wk =  self.ctx.initial_relaxation_wk 
        if not initial_wk.is_finished_ok:
            return self.exit_codes.ERROR_MAIN_WC

        final_wk =  self.ctx.final_relaxation_wk 
        if not final_wk.is_finished_ok:
            return self.exit_codes.ERROR_MAIN_WC
        
        s_initial = initial_wk.outputs.output_structure
        s_final = final_wk.outputs.output_structure

        n_images = self.inputs.n_images.value

        #
        # Add here any heuristics, before handling the
        # path for further refinement
        #
        # starting_path = ....
        #
        #
        # We will need a more general refiner, with an
        # actual path, and not just end-points
        #
        # refined_path = refine_neb_path(starting_path)
        
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
        
    
    def run_NEB_workchain(self):

        inputs = self.exposed_inputs(SiestaBaseNEBWorkChain, namespace='neb')

        print(inputs)
        
        inputs['starting_path'] = self.ctx.path

        running = self.submit(SiestaBaseNEBWorkChain, **inputs)

        self.report(f'Launched SiestaBaseNEBWorkChain<{running.pk}> to find MEP for {self.ctx.atom_symbol} interstitial diffusion.')

        return ToContext(neb_wk=running)

    def check_results(self):

        """
        All checks are done in the NEB workchain
        """

        if not self.ctx.neb_wk.is_finished_ok:
                return self.exit_codes.ERROR_NEB_WK

        outps = self.ctx.neb_wk.outputs
        self.out('neb_output_package', outps['neb_output_package'])

        self.report(f'InterstitialBarrier workchain done.')
            

#    @classmethod
#    def inputs_generator(cls):  # pylint: disable=no-self-argument,no-self-use
#        from aiida_siesta.utils.inputs_generators import BaseWorkChainInputsGenerator
#        return BaseWorkChainInputsGenerator(cls)
