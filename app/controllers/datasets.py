from flask import Blueprint

bp = Blueprint('datasets', __name__)

@bp.get('/datasets/<dataset_id>')
def fetch_dataset(dataset_id):
    return 'Datasets'

@bp.post('/datasets')
def create_dataset():
    return 'Post Datasets'

@bp.put('/datasets/<dataset_id>')
def update_dataset(dataset_id):
    return 'Update Dataset'

@bp.delete('/datasets/<dataset_id>')
def disable_dataset(dataset_id):
    return 'Disable Dataset'
