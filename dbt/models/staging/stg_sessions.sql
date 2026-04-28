with source as (
    select * from {{ source('raw', 'sessions') }}
),

cleaned as (
    select
        title,
        playlist_url,
        created_at,
        cast(duration_s as integer)  as duration_s,
        round(duration_s / 60.0, 1)  as duration_min,
        track_count,
        cast(date_trunc('day', created_at) as date) as session_date
    from source
    where title is not null
      and duration_s > 0
)

select * from cleaned
