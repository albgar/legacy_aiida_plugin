from aiida import orm
from aiida.engine import WorkChain, ToContext
from aiida_siesta.workflows.neb_base import SiestaBaseNEBWorkChain
from aiida_siesta.workflows.base import SiestaBaseWorkChain

from aiida.orm.nodes.data.structure import Site
from aiida_siesta.utils.structures import find_mid_path_position
from aiida_siesta.utils.structures import find_intermediate_structure
from aiida_siesta.utils.interpol import interpolate_two_structures_ase

class VacancyExchangeBarrierWorkChain(WorkChain):

    """
    Workchain to compute the barrier for exchange of a vacancy and an atom
    in a structure. 
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

        spec.input('vacancy_index', valid_type=orm.Int,  
                   help='Index of vacancy in structure')
        spec.input('atom_index', valid_type=orm.Int, 
                   help='Index of atom (to be exchanged) in structure')
        # not implemented yet
        spec.input('migration_direction', valid_type=orm.List, required=False,
                   help='Migration direction (in lattice coordinates)')

        spec.input('n_images', valid_type=orm.Int,
                   help='Number of (internal) images in Path (odd!!)') # validate

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
        spec.exit_code(250, 'ERROR_CONFIG', message='Cannot generate initial path correctly')
        spec.exit_code(300, 'ERROR_NEB_WK', message='SiestaBaseNEBWorkChain did not finish correctly')

    def prepare_structures(self):
        """
        Generate structures: 
            initial: host with the vacancy site removed
            final:   as the initial, but with the coordinates of the 
                     moving atom set to those of the original vacancy.
        """

        s_host = self.inputs.host_structure

        iv = self.inputs.vacancy_index.value
        ia = self.inputs.atom_index.value

        sites = s_host.sites
        atom_site = sites[ia]
        
        s_initial = s_host.clone()
        s_initial.clear_sites()
        
        new_sites = sites
        vacancy_site = new_sites.pop(iv)     # Remove site from list
        vacancy_position = vacancy_site.position
        
        [ s_initial.append_site(s) for s in new_sites ]
        new_ia = new_sites.index(atom_site)  # Atom index might have changed with removal of vacancy

        # Insert site with final position of atom in place of the original.
        new_atom_site = Site(kind_name=atom_site.kind_name, position=vacancy_position)
        new_sites[new_ia] = new_atom_site
        
        s_final = s_initial.clone()
        s_final.clear_sites()
        [ s_final.append_site(s) for s in new_sites ]

        self.ctx.s_initial = s_initial
        self.ctx.s_final = s_final
        self.ctx.vacancy_position = vacancy_position
        self.ctx.atom_site_index = new_ia

        self.report(f'Created initial and final structures')

    def relax_initial(self):
        """
        Run the SiestaBaseWorkChain, might be a relaxation or a scf only.
        """

        inputs = self.exposed_inputs(SiestaBaseWorkChain,
                                     namespace='initial')
        inputs['structure'] = self.ctx.s_initial

        #
        # Update basis dict with floating orbitals at vacancy site
        # (and at 'atom' site, for symmetry)
        ###        original_basis_dict = inputs['basis'].get_dict()

        # Update params dict with constraints for floating orbitals
        ###   original_params = inputs['parameters'].get_dict()


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
        Perhaps more heuristics are needed?
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

        if 'migration_direction' in self.inputs:

            migration_direction = self.inputs.migration_direction.get_list()

            pos1 = s_initial.sites[self.ctx.atom_site_index].position
            pos2 = self.ctx.vacancy_position
            atom_mid_path_position = find_mid_path_position(s_initial,
                                                            pos1, pos2,
                                                            migration_direction)
            self.report(f"Using mid-path point {atom_mid_path_position}")
            
            s_intermediate = find_intermediate_structure(s_initial,
                                                         self.ctx.atom_site_index,
                                                         atom_mid_path_position)
    
            # The starting_path is now built from two sections
            # We assume that the number of internal images is odd,
            # so that n_images // 2 is the number of internal images
            # of each section

            first_list = interpolate_two_structures_ase(s_initial,
                                                        s_intermediate,
                                                        n_images//2)
            second_list = interpolate_two_structures_ase(s_intermediate,
                                                         s_final,
                                                         n_images//2)

            #
            # Remove duplicate central point
            #
            images_list = first_list[:-1] + second_list
        
            if len(images_list) != n_images+2:
                self.report(f"Number of images: {n_images} /= list length")
                return self.exit_codes.ERROR_CONFIG

        else:
            # Just normal (idpp) interpolation
            images_list = interpolate_two_structures_ase(s_initial,
                                                        s_final,
                                                        n_images)
            
            
        #
        # We might need a more general refiner, starting
        # with the trial path
        #
        # refined_path = refine_neb_path(starting_path)
        

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

        self.report(f'Launched SiestaBaseNEBWorkChain<{running.pk}> to find MEP for vacancy exchange.')

        return ToContext(neb_wk=running)

    def check_results(self):

        """
        All checks are done in the NEB workchain
        """

        if not self.ctx.neb_wk.is_finished_ok:
                return self.exit_codes.ERROR_NEB_WK

        outps = self.ctx.neb_wk.outputs
        self.out('neb_output_package', outps['neb_output_package'])

        self.report(f'VacancyExchangeBarrier workchain done.')
            

#    @classmethod
#    def inputs_generator(cls):  # pylint: disable=no-self-argument,no-self-use
#        from aiida_siesta.utils.inputs_generators import BaseWorkChainInputsGenerator
#        return BaseWorkChainInputsGenerator(cls)
