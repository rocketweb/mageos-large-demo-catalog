"""Allow generation for fully inspected profiles; never grant export acceptance."""
import json


def apply_direct_holds(run, visual_receipt):
    from bulk_expansion_images import connect, reject_image
    db = connect(run)
    try:
        items = json.loads(visual_receipt.read_text())['images']
        for item in items:
            if item.get('decision') != 'repair_required':
                continue
            row = db.execute('SELECT state,image_sha256 FROM jobs WHERE job_id=?', (item['job_id'],)).fetchone()
            if row and row['image_sha256'] == item['image_sha256'] and row['state'] != 'rejected':
                reject_image(run, item['job_id'], item['observations'])
    finally:
        db.close()


def profile_key(job):
    if job.get('lane') not in {'existing-categories', 'expanded-categories'} or not job.get('profile'):
        return None
    return job['lane'], job['profile']


def admitted_profiles(db, desc, visual_receipt):
    from bulk_expansion_images import current_job_accepted
    observations = json.loads(visual_receipt.read_text())['images']
    direct = {item['job_id']: item for item in observations}
    if len(direct) != len(observations):
        raise ValueError('Duplicate direct inspection records')
    groups = {}
    for row in db.execute('SELECT * FROM jobs WHERE pilot=1 ORDER BY ordinal'):
        key = profile_key(json.loads(row['request']))
        if key is None:
            continue
        item = direct.get(row['job_id'], {})
        passed = (item.get('image_sha256') == row['image_sha256']
                  and item.get('decision') == 'no_blocking_defect_seen'
                  and bool(item.get('observations'))
                  and current_job_accepted(db, row, desc['review_identity']))
        groups[key] = groups.get(key, True) and passed
    return {key for key, passed in groups.items() if passed}
