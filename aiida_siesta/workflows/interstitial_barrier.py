from aiida import orm
from aiida.engine import WorkChain, calcfunction, ToContext
from aiida.common import AttributeDict
from aiida_siesta.workflows.neb import NEBWorkChain
from aiida_siesta.utils.structures import clone_aiida_structure

class InterstitialBarrierWorkChain(WorkChain):

    """
    Workchain to run a NEB MEP optimization
    starting from two end-point structures
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.expose_inputs(NEBWorkChain,
                           exclude=('initial_structure',
                                    'final_structure', 'neb.structure')
        )

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


        spec.expose_outputs(NEBWorkChain)

        spec.outline(

            cls.prepare_structures,
            cls.prepare_initial_path,
            cls.run_NEB_workchain,
            cls.check_results
        )
        spec.exit_code(200, 'ERROR_CONFIG', message='Cannot figure out interstitial position(s)')
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

        s_initial.append_atom(symbols=atom_symbol,
                             position=initial_position,
                             name=atom_symbol+ '_int')

        s_final.append_atom(symbols=atom_symbol,
                             position=final_position,
                             name=atom_symbol+ '_int')

        self.ctx.s_initial = s_initial
        self.ctx.s_final = s_final
        self.ctx.atom_symbol = atom_symbol

        self.report(f'Created initial and final structures')

    def prepare_initial_path(self):
        """
        Nothing special to do for the interstitial case. If needed, a subclass might implement
        special heuristics to avoid bad guesses for specific cases.
        NOTE however, that currently there is no slot downstream for a guessed path. This will
        be implemented in a NEBBaseWorkChain.
        """
        pass
    
    def run_NEB_workchain(self):

        inputs = self.exposed_inputs(NEBWorkChain)

        inputs['initial_structure'] = self.ctx.s_initial
        inputs['final_structure'] = self.ctx.s_final

        #
        # Reference structure
        #
        inputs['neb']['structure'] = self.ctx.s_initial
        
        print(inputs)
        
        running = self.submit(NEBWorkChain, **inputs)
        self.report(f'Launched NEBWorkChain<{running.pk}> to find MEP for {self.ctx.atom_symbol} interstitial diffusion.')

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
