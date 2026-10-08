from django.db import migrations


def configure_email(apps,schema_editor):
    Workspace=apps.get_model('books','Workspace')
    AuditEvent=apps.get_model('books','AuditEvent')
    for workspace in Workspace.objects.select_related('owner').iterator():
        owner=workspace.owner
        if not owner.email and '@' in owner.username:
            owner.email=owner.username
            owner.save(update_fields=['email'])
            AuditEvent.objects.create(workspace=workspace,actor=None,action='auth.email_configured',details={'account':owner.username,'source':'Owner email migration'})


class Migration(migrations.Migration):
    dependencies=[('books','0005_auththrottle_alter_auditevent_actor')]
    operations=[migrations.RunPython(configure_email,migrations.RunPython.noop)]
