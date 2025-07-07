import struct


class CadModel:
    """A class for importing and representing a 3D CAD model made of triangle facets. Supports reading from binary STL files.
    Attributes:
        name (str): The name of the model, derived from the filename.
        filename (str): The full path to the file. (stored in '/cad_files')
        triangle_normals (list): A list of normal vectors for each triangle facet in the model.
        triangles (list): A list of triangle facets, where each facet is a tuple containing the normal vector and a list of three vertices.
    """
    def __init__(self, filename, name=None):
        # Remove the file extension from the filename for the name attribute, and handle both absolute and relative paths.
        if not name:
            name = filename.split('/')[-1].rsplit('.', 1)[0] if '/' in filename else filename.rsplit('.', 1)[0]

        self.name = name
        self.filename = filename
        self.triangle_normals = []
        self.triangles = []

        if filename.lower().endswith('.stl'):
            normals, triangles = self.read_stl_binary()
            self.triangle_normals = normals
            self.triangles = triangles


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
