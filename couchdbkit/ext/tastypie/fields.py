from tastypie.bundle import Bundle
from tastypie.fields import ListField, DictField

from .resources import DocumentResource


class SchemaListField(ListField):
    def dehydrate(self, bundle):
        if self.attribute is not None:
            final_fields = {}
            obj = getattr(bundle.obj, self.attribute)
            schema = obj.schema()

            # Create fields for the couch object
            for f in schema._properties.values():
                kwargs = {
                    'attribute': f.name,
                    'blank': not f.required,
                    'default': f.default,
                }

                api_field_class = DocumentResource.api_field_from_couch_field(f)

                final_fields[f.name] = api_field_class(**kwargs)
                final_fields[f.name].instance_name = f.name

            # Run through the list and dehydrate each item
            obj_data = []
            for item in obj:
                obj_bundle = Bundle(item)
                for field_name, field_object in final_fields.items():
                    obj_bundle.data[field_name] = field_object.dehydrate(obj_bundle)
                obj_data.append(obj_bundle)

            return self.convert(obj_data)

        if self.has_default():
            return self.convert(self.default)
        else:
            return None

    def hydrate(self, bundle):
        return bundle


# TODO: Implament this, not currently used
class SchemaDictField(DictField):
    def dehydrate(self, bundle):
        raise NotImplemented

    def hydrate(self, bundle):
        raise NotImplemented

    # def dehydrate(self, bundle):
    #     if self.attribute is not None:
    #         final_fields = {}
    #         obj_attribute = getattr(bundle.obj, self.attribute)
    #         schema = obj_attribute.schema()
    # 
    #         for f in schema._properties.values():
    #             kwargs = {
    #                 'attribute': f.name,
    #                 'blank': not f.required,
    #                 'default': f.default,
    #             }
    # 
    #             api_field_class = DocumentResource.api_field_from_couch_field(f)
    # 
    #             final_fields[f.name] = api_field_class(**kwargs)
    #             final_fields[f.name].instance_name = f.name
    # 
    #         sub_bundle = Bundle(obj_attribute)
    #         for field_name, field_object in final_fields.items():
    #             sub_bundle.data[field_name] = field_object.dehydrate(sub_bundle)
    # 
    #         return self.convert(sub_bundle)
    # 
    #     if self.has_default():
    #         return self.convert(self.default)
    #     else:
    #         return None
