from flask_restx import Namespace, fields

namespace = Namespace('datasets', 'Dataset operations')

dataset_model = namespace.model('Dataset', {
    'id': fields.String(readonly=True, required=True, description='Dataset ID'),
    'name': fields.Raw(required=True, description='Dataset name'),
    'data': fields.String(required=False, description='Dataset information'),
    'is_enabled': fields.Boolean(required=True, description='Dataset status')
})

dataset_create_model = namespace.model('DatasetCreate', {
    'id': fields.String(readonly=True, required=True, description='Dataset ID')
})

dataset_filter_model = namespace.model('DatasetFilter', {
    'id': fields.String(readonly=True, required=True, description='Filter ID'),
    'options': fields.List(
        fields.Nested({
            'id': fields.String(required=True, description='Options ID'),
            'label': fields.String(required=True, description='Options label'),
            'value': fields.String(required=True, description='Options value')
        }
    )),
    'selection': fields.String(required=True, description='Filter selection'),
    'title': fields.String(required=True, description='Filter title') 
})