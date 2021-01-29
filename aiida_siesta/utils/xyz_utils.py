#
# Simple parser for xyz file
#
def get_positions_from_xyz_file(file):

    positions = []
    with open(file,'r') as fh:
        lines=fh.readlines()
        for line in lines[2:]:
            parts = line.split()
            # Support the case in which the species label is present
            if len(parts) == 4:
                start = 1
            else:
                start = 0
            pos = [ float(i) for i in parts[start:] ]
            positions.append(pos)
                    
    return positions

def get_structure_list_from_folder(folder,ref_struct):

    import glob

    xyz_list = glob.glob("{}/*.xyz".format(folder))
    xyz_list.sort()

    structure_list = []
    for file in xyz_list:
        positions = get_positions_from_xyz_file(file)
        s = ref_struct.clone()
        s.reset_sites_positions(positions)
        structure_list.append(s)

    return structure_list

def write_xyz_file_from_structure(s, filename, labels=True):

   xyz_tuple = s._prepare_xyz()

   if labels:
       # We add the labels
       open(filename, 'wb').write(xyz_tuple[0])
   else:
       # We need to remove the labels
       # First, turn bytes into string and split
       lines = xyz_tuple[0].decode().split("\n")
       with open(filename,"w") as f:
           #
           # Write first two lines
           #
           f.write("{}\n".format(lines[0]))
           f.write("{}\n".format(lines[1]))
           #
           # Write only positions
           #
           for line in lines[2:] :
               pos = line.split()[1:]
               f.write("{} {} {}\n".format(pos[0],pos[1],pos[2]))
               

    