from django.db import migrations


def add_accounts(apps, schema_editor):
    Workspace=apps.get_model('books','Workspace')
    Account=apps.get_model('books','Account')
    for workspace in Workspace.objects.iterator():
        if Account.objects.filter(workspace=workspace,code='opening_equity').exists():
            continue
        name='Opening balance equity'
        suffix=1
        while Account.objects.filter(workspace=workspace,name=name).exists():
            name=f'Opening balance equity (system {suffix})'
            suffix+=1
        Account.objects.create(workspace=workspace,name=name,kind='equity',code='opening_equity')


class Migration(migrations.Migration):
    dependencies=[('books','0003_remove_voucher_valid_voucher_kind_alter_voucher_kind_and_more')]
    # Preserve created financial master records when rolling back schema versions.
    operations=[migrations.RunPython(add_accounts,migrations.RunPython.noop)]
