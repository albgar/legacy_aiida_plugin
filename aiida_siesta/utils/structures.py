#
#
#
def clone_aiida_structure (s):
    """
    A cloned structure is not quite ready to store more atoms. 
    This function fixes it
    """

    t=s.clone()
    t._internal_kind_tags={}

    return t

def aiida_struct_to_ase (s):
    """
    This is a custom version to bypass the inappropriate implementation
    of the site.get_ase() routine (it does not set tags for sites whose
    names coincide with the atomic symbol...). Here we always set the
    tag to the "species number", which is the "kind number" + 1.
    """

    import ase

    # Build a "species dictionary" mapping kind names to tags (starting at 1)
    _kinds = s.kinds
    sp_index = {}
    for i in range(len(_kinds)):
        sp_index[_kinds[i].name] = i + 1

    s_ase = ase.Atoms(cell=s.cell, pbc=s.pbc)

    for site in s.sites:
        ase_atom = site.get_ase(kinds=_kinds)
        ase_atom.tag = sp_index[site.kind_name]
        s_ase.append(ase_atom)
        
    return s_ase

#
#
def ase_struct_to_aiida(s_ase, kinds):
    """
    Converts an ASE structure object to an equivalent AiiDA object,
    preserving the kind names.
    :param: s_ase: The ASE object
    :param: kinds: The kinds object of a reference AiiDA structure
    """
    
    from aiida.orm import StructureData
    import ase

    s = StructureData(cell=s_ase.cell)

    positions = s_ase.positions
    tags = s_ase.get_tags()

    for i in range(len(positions)):
        kind = kinds[tags[i]-1]
        s.append_atom(position=positions[i],symbols=kind.symbol, name=kind.name)

    return s

    
