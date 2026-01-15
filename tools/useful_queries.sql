-- useful queries

-- datasets with processing status
select id, name, file_collocation_status from datasets where file_collocation_status = 'processing';

-- datasets with no collocation status
select count(*) from datasets where file_collocation_status is null;

-- datasets with no collocation status and ordered by created_at
SELECT id, name, is_enabled, file_collocation_status 
FROM datasets 
WHERE file_collocation_status IS NULL
ORDER BY created_at ASC
LIMIT 10;

-- file details
SELECT df.*, d.id
  FROM data_files df
  JOIN dataset_versions_data_files dvdf ON df.id = dvdf.data_file_id
  JOIN dataset_versions dv ON dvdf.dataset_version_id = dv.id
  JOIN datasets d ON dv.dataset_id = d.id
  where df.storage_file_name = '{file_name}';

 -- Total files pending migration (datasets not yet completed)
  SELECT COUNT(DISTINCT df.id) as total_files_pending
  FROM data_files df
  JOIN dataset_versions_data_files dvdf ON df.id = dvdf.data_file_id
  JOIN dataset_versions dv ON dvdf.dataset_version_id = dv.id
  JOIN datasets d ON dv.dataset_id = d.id
  WHERE d.is_enabled = true
    AND (d.file_collocation_status IS NULL
         OR d.file_collocation_status IN ('pending', 'processing'));

-- Files grouped by collocation status
  SELECT
      COALESCE(d.file_collocation_status::text, 'NULL (legacy)') as status,
      COUNT(DISTINCT d.id) as num_datasets,
      COUNT(DISTINCT df.id) as num_files,
      SUM(df.size_bytes) as total_size_bytes,
      ROUND(SUM(df.size_bytes) / 1024.0 / 1024.0 / 1024.0, 2) as total_size_gb
  FROM datasets d
  JOIN dataset_versions dv ON d.id = dv.dataset_id
  JOIN dataset_versions_data_files dvdf ON dv.id = dvdf.dataset_version_id
  JOIN data_files df ON dvdf.data_file_id = df.id
  WHERE d.is_enabled = true
  GROUP BY d.file_collocation_status
  ORDER BY
      CASE
          WHEN d.file_collocation_status IS NULL THEN 0
          WHEN d.file_collocation_status = 'pending' THEN 1
          WHEN d.file_collocation_status = 'processing' THEN 2
          WHEN d.file_collocation_status = 'completed' THEN 3
      END;
	  

-- Progress summary with time estimate
  WITH stats AS (
      SELECT
          COUNT(DISTINCT df.id) FILTER (
              WHERE d.file_collocation_status = 'completed'
          ) as completed_files,
          COUNT(DISTINCT df.id) FILTER (
              WHERE d.file_collocation_status IS NULL
                 OR d.file_collocation_status IN ('pending', 'processing')
          ) as pending_files,
          COUNT(DISTINCT df.id) as total_files
      FROM data_files df
      JOIN dataset_versions_data_files dvdf ON df.id = dvdf.data_file_id
      JOIN dataset_versions dv ON dvdf.dataset_version_id = dv.id
      JOIN datasets d ON dv.dataset_id = d.id
      WHERE d.is_enabled = true
  )
  SELECT
      total_files,
      completed_files,
      pending_files,
      ROUND(100.0 * completed_files / NULLIF(total_files, 0), 2) as percent_complete,
      -- Time estimate at 20 files/sec
      pending_files / 20.0 as seconds_remaining,
      ROUND((pending_files / 2.7) / 60.0, 2) as minutes_remaining,
      ROUND((pending_files / 2.7) / 3600.0, 2) as hours_remaining
  FROM stats;

-- Datasets stuck in processing status for more than 1 hour
  SELECT
      d.id,
      d.name,
      d.file_collocation_status,
      d.updated_at,
      COUNT(DISTINCT df.id) as num_files,
      EXTRACT(EPOCH FROM (NOW() - d.updated_at)) / 60 as minutes_in_processing
  FROM datasets d
  JOIN dataset_versions dv ON d.id = dv.dataset_id
  JOIN dataset_versions_data_files dvdf ON dv.id = dvdf.dataset_version_id
  JOIN data_files df ON dvdf.data_file_id = df.id
  WHERE d.file_collocation_status = 'processing'
    AND d.updated_at < NOW() - INTERVAL '1 hour'
  GROUP BY d.id, d.name, d.file_collocation_status, d.updated_at
  ORDER BY d.updated_at ASC;
  

 -- Files completed in the last hour
  SELECT
      COUNT(DISTINCT df.id) as files_completed_last_hour,
      COUNT(DISTINCT df.id) / 3600.0 as avg_files_per_second
  FROM data_files df
  JOIN dataset_versions_data_files dvdf ON df.id = dvdf.data_file_id
  JOIN dataset_versions dv ON dvdf.dataset_version_id = dv.id
  JOIN datasets d ON dv.dataset_id = d.id
  WHERE d.file_collocation_status = 'completed'
    AND d.updated_at > NOW() - INTERVAL '1 hour';

-- Arquivos ainda no root (legacy path) - não movidos
SELECT 
    d.id as dataset_id,
    d.name as dataset_name,
    d.is_enabled,
    d.file_collocation_status,
    COUNT(f.id) as pending_files
FROM datasets d
JOIN data_files f ON f.id = d.id
WHERE f.storage_path ~ '^datamap/[a-f0-9]{32}$'  -- só hash, sem path de data
GROUP BY d.id, d.name, d.is_enabled, d.file_collocation_status
ORDER BY pending_files DESC;

-- Resumo geral de migração
SELECT 
    CASE 
        WHEN storage_path ~ '^datamap/[a-f0-9]{32}$' THEN 'legacy'
        WHEN storage_path ~ '^datamap/\d{4}/' THEN 'organized'
        ELSE 'other'
    END as path_type,
    COUNT(*) as file_count
FROM data_files
GROUP BY path_type;

-- Datasets disabled com arquivos pendentes
SELECT 
    d.id,
    d.name,
    d.file_collocation_status,
    COUNT(f.id) as pending_files
FROM datasets d
JOIN data_files f ON f.id = d.id
WHERE d.is_enabled = false
  AND f.storage_path ~ '^datamap/[a-f0-9]{32}$'
GROUP BY d.id, d.name, d.file_collocation_status;

-- Arquivos onde o storage_file_name aparece tanto em legacy quanto em organized
-- Arquivos que aparecem com path organized mas hash ainda existe como legacy
SELECT 
    df.id,
    df.name,
    df.storage_file_name,
    df.storage_path,
    d.id as dataset_id,
    d.name as dataset_name
FROM data_files df
JOIN dataset_versions_data_files dvdf ON df.id = dvdf.data_file_id
JOIN dataset_versions dv ON dvdf.dataset_version_id = dv.id
JOIN datasets d ON dv.dataset_id = d.id
WHERE df.storage_path ~ '^datamap/\d{4}/'
  AND df.storage_file_name IN (
    SELECT df2.storage_file_name 
    FROM data_files df2 
    WHERE df2.storage_path ~ '^datamap/[a-f0-9]{32}$'
  )
LIMIT 100;

SELECT storage_path FROM data_files 
WHERE storage_path !~ '^datamap/[a-f0-9]{32}$'
  AND storage_path !~ '^datamap/\d{4}/';

  SELECT storage_path, storage_file_name 
FROM data_files 
WHERE storage_path ~ '^datamap/\d{4}/';

-- Exporta todos os storage_file_name que estão como legacy no banco
SELECT storage_file_name 
FROM data_files 
WHERE storage_path ~ '^datamap/[a-f0-9]{32}$';

-- Confirma: arquivos no banco que são legacy (ainda no root)
SELECT COUNT(*) FROM data_files 
WHERE storage_path ~ '^datamap/[a-f0-9]{32}$';
-- Deveria dar ~74.138 (92.276 - 18.138)

-- Arquivos legacy de datasets desabilitados
SELECT 
    COUNT(df.id) as file_count,
    SUM(df.size_bytes) / (1024*1024*1024) as size_gb
FROM data_files df
JOIN dataset_versions_data_files dvdf ON df.id = dvdf.data_file_id
JOIN dataset_versions dv ON dvdf.dataset_version_id = dv.id
JOIN datasets d ON dv.dataset_id = d.id
WHERE df.storage_path ~ '^datamap/[a-f0-9]{32}$'
  AND d.is_enabled = false;
