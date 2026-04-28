with source as (
    select * from {{ source('raw', 'feedback') }}
),

cleaned as (
    select
        session_title,
        rating                                       as rating_raw,
        case
            when rating like '%Great%' then 'Great'
            when rating like '%Okay%'  then 'Okay'
            when rating like '%Hard%'  then 'Hard'
            else 'Unknown'
        end                                          as rating,
        note,
        created_at,
        cast(date_trunc('day', created_at) as date)  as feedback_date
    from source
    where session_title is not null
)

select * from cleaned
