import logging
from app.models.datasets import Datasets
from app import db
from sqlalchemy import or_, cast, String

class DatasetRepository:
    def fetch(self, dataset_id, is_enabled=True):
        return Datasets.query.filter_by(id=dataset_id, is_enabled=is_enabled).first()
    
    def upsert(self, dataset):
        if (dataset.id is None):
            db.session.add(dataset)
        db.session.commit()
        db.session.refresh(dataset)
        return dataset
        
    def search(self, query_params):
        query = db.session.query(Datasets)

        search_conditions = []
        
        if query_params['categories']:
            for category in query_params['categories']:
                search_term = f'%{category.strip()}%'
                search_conditions.append(Datasets.data['category'].astext.ilike(search_term))
        
        if query_params['data_types']:
            for data_type in query_params['data_types']:
                search_term = f'%{data_type.strip()}%'
                search_conditions.append(Datasets.data['data_type'].astext.ilike(search_term))
        
        if query_params['level']:
            search_conditions.append(Datasets.data['level'].astext.ilike(query_params['level']))

        if search_conditions:
            query = query.filter(*search_conditions)

        if query_params['date_from']:
            query = query.filter(Datasets.created_at >= query_params['date_from'])
        
        if query_params['date_to']:
            query = query.filter(Datasets.created_at <= query_params['date_to'])
        
        if query_params['full_text']:
            search_term = f'%{query_params["full_text"]}%'
            query = query.filter(or_(cast(Datasets.data, String).ilike(search_term), Datasets.name.ilike(search_term)))
        
        return query.all()
