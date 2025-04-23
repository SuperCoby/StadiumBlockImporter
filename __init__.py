bl_info = {
    "name": "Stadium COB Block Importer",
    "blender": (4, 0, 0),
    "category": "3D View",
    "author": "SuperCoby",
    "version": (1, 0, 0),
    "location": "View3D > Sidebar > Extras",
    "description": "Importe les blocs .cob depuis le fichier Model/StadiumModel.cob",
}

import bpy
import struct
import os

# Addon Preferences
class StadiumCobAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    textures_path: bpy.props.StringProperty(
        name="Textures Folder",
        subtype='DIR_PATH',
        description="Chemin vers le dossier contenant les textures .png/.jpg"
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "textures_path")

# Lire la liste des blocs
def list_cob_block_names(filepath, keyword=""):
    names = []
    if not os.path.exists(filepath):
        return []

    keyword = keyword.lower().strip()

    with open(filepath, 'rb') as file:
        if file.read(5) != b'COB3D':
            return []

        num_objects = struct.unpack('I', file.read(4))[0]
        for _ in range(num_objects):
            name_length = struct.unpack('I', file.read(4))[0]
            name = file.read(name_length).decode('utf-8')

            if not keyword or keyword in name.lower():
                names.append(name)

            num_materials = struct.unpack('I', file.read(4))[0]
            for _ in range(num_materials):
                file.read(struct.unpack('I', file.read(4))[0])
                file.read(12)
                file.read(struct.unpack('I', file.read(4))[0])
            file.read(struct.unpack('I', file.read(4))[0] * 12)
            for _ in range(struct.unpack('I', file.read(4))[0]):
                v = struct.unpack('I', file.read(4))[0]
                file.read(v * 4)
                file.read(4)
            file.read(struct.unpack('I', file.read(4))[0] * 8)
    return names

# Mettre à jour la liste selon filtre
def update_block_list(self, context):
    keyword = context.scene.block_filter
    names = list_cob_block_names(context.scene.import_path, keyword)
    context.scene["_block_enum_items"] = names

# Importer depuis COB
def import_from_cob(filepath):
    if not os.path.exists(filepath):
        print("❌ File not found.")
        return

    prefs = bpy.context.preferences.addons[__name__].preferences
    textures_path = bpy.path.abspath(prefs.textures_path)

    if not os.path.isdir(textures_path):
        self.report({'WARNING'}, "❗ Textures folder not defined.")
        return

    selected = bpy.context.scene.block_name_enum
    keyword = bpy.context.scene.block_filter.strip().lower()
    match_all_filtered = (selected == "ALL")

    with open(filepath, 'rb') as file:
        if file.read(5) != b'COB3D':
            print("❌ Invalid .cob file.")
            return

        num_objects = struct.unpack('I', file.read(4))[0]

        for _ in range(num_objects):
            name_length = struct.unpack('I', file.read(4))[0]
            name = file.read(name_length).decode('utf-8')

            should_import = False
            if selected == name:
                should_import = True
            elif match_all_filtered and (not keyword or keyword in name.lower()):
                should_import = True

            if not should_import:
                num_materials = struct.unpack('I', file.read(4))[0]
                for _ in range(num_materials):
                    file.read(struct.unpack('I', file.read(4))[0])
                    file.read(12)
                    file.read(struct.unpack('I', file.read(4))[0])
                file.read(struct.unpack('I', file.read(4))[0] * 12)
                for _ in range(struct.unpack('I', file.read(4))[0]):
                    v = struct.unpack('I', file.read(4))[0]
                    file.read(v * 4)
                    file.read(4)
                file.read(struct.unpack('I', file.read(4))[0] * 8)
                continue

            mesh = bpy.data.meshes.new(name)
            obj = bpy.data.objects.new(name, mesh)

            num_materials = struct.unpack('I', file.read(4))[0]
            materials = []
            for _ in range(num_materials):
                mat_name = file.read(struct.unpack('I', file.read(4))[0]).decode('utf-8')
                color = struct.unpack('3f', file.read(12))
                material = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
                material.diffuse_color = (*color, 1.0)
                img_path = file.read(struct.unpack('I', file.read(4))[0]).decode('utf-8')

                image = None
                if img_path:
                    full_path = os.path.join(textures_path, os.path.basename(img_path))
                    if os.path.exists(full_path):
                        image = bpy.data.images.load(full_path)

                material.use_nodes = True
                nodes = material.node_tree.nodes
                links = material.node_tree.links
                nodes.clear()
                bsdf = nodes.new("ShaderNodeBsdfPrincipled")
                output = nodes.new("ShaderNodeOutputMaterial")
                links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
                if image:
                    tex = nodes.new("ShaderNodeTexImage")
                    tex.image = image
                    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
                materials.append(material)

            verts = [struct.unpack('3f', file.read(12)) for _ in range(struct.unpack('I', file.read(4))[0])]
            faces, face_materials = [], []
            for _ in range(struct.unpack('I', file.read(4))[0]):
                f = [struct.unpack('I', file.read(4))[0] for _ in range(struct.unpack('I', file.read(4))[0])]
                faces.append(f)
                face_materials.append(struct.unpack('I', file.read(4))[0])
            mesh.from_pydata(verts, [], faces)
            mesh.update()

            for mat in materials:
                mesh.materials.append(mat)
            for i, poly in enumerate(mesh.polygons):
                poly.material_index = face_materials[i]

            uv_layer = mesh.uv_layers.new()
            for i in range(struct.unpack('I', file.read(4))[0]):
                uv = struct.unpack('2f', file.read(8))
                uv_layer.data[i].uv = uv

            bpy.context.collection.objects.link(obj)

    print("✅ Import completed.")

# Interface dans la vue 3D
class CobPanel(bpy.types.Panel):
    bl_label = "COB Importer"
    bl_idname = "OBJECT_PT_cob_import"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = ".cob"

    def draw(self, context):
        layout = self.layout
        prefs = bpy.context.preferences.addons[__name__].preferences

        if prefs.textures_path.strip() != "":
            layout.prop(context.scene, "block_filter", text="Filter")
            layout.prop(context.scene, "block_name_enum", text="Block List")
            layout.operator("object.import_cob", text="Import Block")
        else:
            layout.label(text="Set the textures folder in preferences", icon="ERROR")

class ImportCobOperator(bpy.types.Operator):
    bl_idname = "object.import_cob"
    bl_label = "Import COB Block"

    def execute(self, context):
        import_from_cob(context.scene.import_path)
        return {'FINISHED'}

def get_block_enum_items(self, context):
    items = context.scene.get("_block_enum_items", [])
    sorted_items = sorted(items, key=str.lower)
    return [("ALL", "All Blocks", "")] + [(n, n, "") for n in sorted_items]

def register():
    bpy.utils.register_class(StadiumCobAddonPreferences)
    bpy.utils.register_class(CobPanel)
    bpy.utils.register_class(ImportCobOperator)

    addon_dir = os.path.dirname(__file__)
    cob_path = os.path.join(addon_dir, "Model", "StadiumModel.cob")

    bpy.types.Scene.import_path = bpy.props.StringProperty(name="Import Path", subtype="FILE_PATH", default=cob_path)
    bpy.types.Scene.block_filter = bpy.props.StringProperty(name="Filter", update=update_block_list)
    bpy.types.Scene.block_name_enum = bpy.props.EnumProperty(name="Block", items=get_block_enum_items)

    def safe_update_scene_props():
        if bpy.context.scene is None:
            return None
        bpy.context.scene.import_path = cob_path
        if "_block_enum_items" not in bpy.context.scene:
            bpy.context.scene.block_filter = ""
            update_block_list(None, bpy.context)
        return None

    bpy.app.timers.register(safe_update_scene_props, first_interval=0.1)

def unregister():
    bpy.utils.unregister_class(StadiumCobAddonPreferences)
    bpy.utils.unregister_class(CobPanel)
    bpy.utils.unregister_class(ImportCobOperator)

    del bpy.types.Scene.import_path
    del bpy.types.Scene.block_filter
    del bpy.types.Scene.block_name_enum

if __name__ == "__main__":
    register()
