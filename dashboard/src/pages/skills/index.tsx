import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Plus, Pencil, Trash2, Zap } from 'lucide-react'
import { getSkills, getSkillDetail, createSkill, deleteSkill } from '@/shared/api/settings'
import type { Skill } from '@/entities/skill/model'

interface SkillForm {
  name: string
  description: string
  body: string
  tags: string
}

const EMPTY: SkillForm = { name: '', description: '', body: '', tags: '' }

function SkillDialog({
  open,
  initial,
  isEdit,
  onClose,
}: {
  open: boolean
  initial: SkillForm
  isEdit: boolean
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState<SkillForm>(initial)

  const save = useMutation({
    mutationFn: () =>
      createSkill({
        name: form.name.trim(),
        description: form.description.trim(),
        body: form.body.trim(),
        tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skills'] })
      onClose()
    },
  })

  const set = (k: keyof SkillForm, v: string) => setForm((f) => ({ ...f, [k]: v }))

  return (
    <Dialog open={open} onOpenChange={() => onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Skill' : 'New Skill'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-1">
          <div className="space-y-1.5">
            <Label className="text-xs">Name</Label>
            <Input
              placeholder="e.g. daily-briefing"
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              disabled={isEdit}
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Description</Label>
            <Input
              placeholder="What this skill does…"
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Tags (comma-separated)</Label>
            <Input
              placeholder="research, daily, automation"
              value={form.tags}
              onChange={(e) => set('tags', e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Skill body (Markdown)</Label>
            <Textarea
              className="font-mono text-xs min-h-[180px] resize-none"
              placeholder="## Goal&#10;Describe what the agent should do when this skill is triggered.&#10;&#10;## Steps&#10;1. …"
              value={form.body}
              onChange={(e) => set('body', e.target.value)}
              spellCheck={false}
            />
          </div>
          {save.isError && (
            <p className="text-xs text-destructive">{(save.error as Error).message}</p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button
            size="sm"
            onClick={() => save.mutate()}
            disabled={!form.name.trim() || save.isPending}
          >
            {save.isPending ? 'Saving…' : isEdit ? 'Update' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function SkillsPage() {
  const qc = useQueryClient()
  const { data: skills = [], isLoading } = useQuery({ queryKey: ['skills'], queryFn: getSkills })
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editForm, setEditForm] = useState<SkillForm | null>(null)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)

  const remove = useMutation({
    mutationFn: (name: string) => deleteSkill(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skills'] }),
  })

  const openEdit = async (skill: Skill) => {
    try {
      const detail = await getSkillDetail(skill.name)
      setEditForm({
        name: detail.name,
        description: detail.description,
        body: detail.body ?? '',
        tags: (detail.tags ?? []).join(', '),
      })
    } catch {
      setEditForm({
        name: skill.name,
        description: skill.description,
        body: '',
        tags: skill.tags.join(', '),
      })
    }
    setDialogOpen(true)
  }

  const userSkills = skills.filter((s) => !s.builtin)
  const builtinSkills = skills.filter((s) => s.builtin)

  return (
    <div className="space-y-4 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Skills</h2>
          <p className="text-sm text-muted-foreground">
            {userSkills.length} user · {builtinSkills.length} built-in
          </p>
        </div>
        <Button size="sm" onClick={() => { setEditForm(null); setDialogOpen(true) }}>
          <Plus className="h-3.5 w-3.5 mr-1.5" /> New Skill
        </Button>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {userSkills.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">User skills</p>
          {userSkills.map((skill) => (
            <SkillCard
              key={skill.name}
              skill={skill}
              onEdit={() => openEdit(skill)}
              onDelete={() => setPendingDelete(skill.name)}
            />
          ))}
        </div>
      )}

      {builtinSkills.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Built-in skills</p>
          {builtinSkills.map((skill) => (
            <SkillCard key={skill.name} skill={skill} />
          ))}
        </div>
      )}

      {/* Create / Edit dialog */}
      <SkillDialog
        key={editForm?.name ?? '__new__'}
        open={dialogOpen}
        initial={editForm ?? EMPTY}
        isEdit={!!editForm}
        onClose={() => { setDialogOpen(false); setEditForm(null) }}
      />

      {/* Delete confirm */}
      <AlertDialog open={!!pendingDelete} onOpenChange={() => setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete skill "{pendingDelete}"?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes the skill file. Built-in skills are unaffected.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => { if (pendingDelete) { remove.mutate(pendingDelete); setPendingDelete(null) } }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function SkillCard({
  skill,
  onEdit,
  onDelete,
}: {
  skill: Skill
  onEdit?: () => void
  onDelete?: () => void
}) {
  return (
    <Card>
      <CardHeader className="pb-2 flex-row items-start justify-between gap-2">
        <div className="space-y-1 min-w-0">
          <CardTitle className="text-sm flex items-center gap-2">
            <Zap className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            {skill.name}
            {skill.builtin && <Badge variant="secondary" className="text-[10px]">built-in</Badge>}
            {skill.source === 'agent' && <Badge variant="outline" className="text-[10px]">agent-created</Badge>}
          </CardTitle>
          {skill.tags.length > 0 && (
            <div className="flex gap-1 flex-wrap">
              {skill.tags.map((t) => (
                <Badge key={t} variant="outline" className="text-[10px] px-1.5 py-0">{t}</Badge>
              ))}
            </div>
          )}
        </div>
        {!skill.builtin && (
          <div className="flex gap-1 shrink-0">
            {onEdit && (
              <Button size="icon" variant="ghost" className="h-6 w-6" onClick={onEdit}>
                <Pencil className="h-3 w-3" />
              </Button>
            )}
            {onDelete && (
              <Button size="icon" variant="ghost" className="h-6 w-6 text-muted-foreground hover:text-destructive" onClick={onDelete}>
                <Trash2 className="h-3 w-3" />
              </Button>
            )}
          </div>
        )}
      </CardHeader>
      <CardContent className="pb-3">
        <CardDescription className="text-xs">
          {skill.description || <span className="italic">No description</span>}
        </CardDescription>
        {skill.usage_count > 0 && (
          <p className="text-[10px] text-muted-foreground mt-1.5">Used {skill.usage_count}×</p>
        )}
      </CardContent>
    </Card>
  )
}
