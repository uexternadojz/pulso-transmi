"""Versioned representation of already released observations."""


def serialize_observation(row):
    result = {key: row[key] for key in ('station_id', 'observed_at', 'released_at')}
    if row['source_schema_version'] == 1:
        result['demand'] = row['demand']
    else:
        result['schema_version'] = 2
        result['measurement'] = {
            'value': None if row['source_quality'] == 'missing' else f"{row['demand']:.2f}",
            'unit': 'passengers',
            'quality': row['source_quality'],
        }
    return result
