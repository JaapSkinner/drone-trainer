import struct
import numpy as np


class CadMesh:
    """A class for importing and representing a 3D CAD model made of triangle facets. Supports reading from binary STL files.
    Attributes:
        name (str): The name of the model, derived from the filename.
        filename (str): The full path to the file. (stored in '/cad_files')
        triangle_normals (list): A list of normal vectors for each triangle facet in the model.
        triangles (list): A list of triangle facets, where each facet is a tuple containing the normal vector and a list of three vertices.
    """
    def __init__(self, filename, name=None, pose=None, scale=None, colour=None):
        # Remove the file extension from the filename for the name attribute, and handle both absolute and relative paths.
        if not name:
            name = filename.split('/')[-1].rsplit('.', 1)[0] if '/' in filename else filename.rsplit('.', 1)[0]

        self.name = name
        self.filename = filename

        if pose is None:
            pose = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)  # Default pose (Angles in DEG) (x, y, z, x_rot, y_rot, z_rot) Rotation occurs in z then y then x order

        if scale is None:
            scale = (0.05, 0.05, 0.05)  # Default scale (sx, sy, sz)

        if colour is None:
            colour = (0.7, 0.7, 0.7, 1.0)  # Default colour(0 - 1) (r, g, b, a)

        self.pose = pose
        self.scale = scale

        self.face_normals = []
        self.vertex_normals = [] # 2D list of vertex normals, first dimension is polygon index, second dimension is vertex index
        self.polys = []

        self.textures = None  # Placeholder for texture, if needed later

        if filename.lower().endswith('.stl'):
            normals, triangles = self.read_stl_binary()
            self.face_normals = normals
            self.polys = triangles

        elif filename.lower().endswith('.obj'):
            normals, quads = self.read_obj()
            self.vertex_normals = normals
            self.polys = quads

        # each triangle needs a colour, so we use the base colour for all triangles
        self.colour = [colour] * len(self.polys) if self.polys else [colour]


    def read_stl_binary(self):
        """Reads a binary STL file and returns triangle_normals and triangles lists.

        Returns:
            tuple: (triangle_normals, triangles)
        """
        triangle_normals = []
        triangles = []
        try:
            with open(self.filename, 'rb') as f:
                # STL binary files start with an 80-byte header (usually ignored)
                header = f.read(80)
                # Next 4 bytes: number of triangle facets (unsigned int)
                num_facets = struct.unpack('<i', f.read(4))[0]
                for _ in range(num_facets):
                    # Each facet: 12 bytes for normal vector (3 floats)
                    normal = struct.unpack('<3f', f.read(12))
                    vertices = []
                    # Each triangle has 3 vertices, each 12 bytes (3 floats)
                    for _ in range(3):
                        vertices.append(struct.unpack('<3f', f.read(12)))
                    # 2 bytes: attribute byte count (often unused)
                    attribute_byte_count = struct.unpack('<h', f.read(2))
                    triangle_normals.append(normal)
                    triangles.append(vertices)
        except (IOError, struct.error) as e:
            print(f"Error reading STL file: {e}")
        return triangle_normals, triangles

    def read_obj(self):
        """Reads an OBJ file and returns a list of objects, each with triangle_normals and triangles lists.

        Returns:
            tuple: (vertex_normals, polys)

            Note: Does not handle texture coordinates or materials.
        """


        triangle_normals = []
        triangles = []

        points = []
        normals = []
        textures = []
        polys = []
        vertex_normals = []

        try:
            with open(self.filename, 'r') as f:
                for line in f:
                    if line.startswith('v '):
                        points.append(tuple(map(float, line.split()[1:4])))
                    elif line.startswith('vn '):
                        normals.append(tuple(map(float, line.split()[1:4])))
                    elif line.startswith('vt '):
                        textures.append(tuple(map(float, line.split()[1:])))
                    elif line.startswith('f '):
                        parts = line.split()[1:]

                        if len(parts) == 4: # TODO: This only works for quads, does not accept other polygon types
                            v_indices = [int(p.split('/')[0]) - 1 for p in parts]
                            t_indices = [int(p.split('/')[1]) - 1 if '/' in p else None for p in parts]
                            n_indices = [int(p.split('/')[2]) - 1 for p in parts] if '/' in parts[0] else [None] * 3
                            vertex_normals.append([normals[n] for n in n_indices if n is not None])
                            polys.append([points[v] for v in v_indices])

            return vertex_normals, polys

        except IOError as e:
            print(f"Error reading OBJ file: {e}")
        return triangle_normals, triangles
