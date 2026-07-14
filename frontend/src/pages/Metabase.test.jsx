import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Metabase from './Metabase'
import { metabaseAPI } from '../api/client'

// Regression coverage for the bug the user reported live: skills/experience/
// projects could only be added or deleted, never edited, and an experience's
// description had no UI path to set after creation. This exercises the same
// edit -> save -> reload round trip verified manually in the browser.
vi.mock('../api/client', () => ({
  metabaseAPI: {
    getPersonal: vi.fn().mockResolvedValue({ data: {} }),
    savePersonal: vi.fn(),
    getSkills: vi.fn(),
    addSkill: vi.fn(),
    updateSkill: vi.fn(),
    deleteSkill: vi.fn(),
    getProjects: vi.fn().mockResolvedValue({ data: [] }),
    addProject: vi.fn(),
    updateProject: vi.fn(),
    deleteProject: vi.fn(),
    getExperience: vi.fn().mockResolvedValue({ data: [] }),
    addExperience: vi.fn(),
    updateExperience: vi.fn(),
    deleteExperience: vi.fn(),
    importResume: vi.fn(),
  },
}))

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

const SKILL = {
  id: 'skill-1',
  name: 'Python',
  category: 'Programming Languages',
  proficiency: 'Intermediate',
  years_experience: 2,
  is_primary: true,
}

beforeEach(() => {
  vi.clearAllMocks()
  metabaseAPI.getPersonal.mockResolvedValue({ data: {} })
  metabaseAPI.getProjects.mockResolvedValue({ data: [] })
  metabaseAPI.getExperience.mockResolvedValue({ data: [] })
})

describe('Metabase — Skills edit flow', () => {
  it('edits an existing skill and PATCHes the full form, not just the changed field', async () => {
    metabaseAPI.getSkills.mockResolvedValue({ data: [SKILL] })
    metabaseAPI.updateSkill.mockResolvedValue({ data: { ...SKILL, proficiency: 'Expert' } })

    render(<Metabase />)
    await userEvent.click(screen.getByRole('button', { name: 'Skills' }))

    const skillRow = (await screen.findByText('Python')).closest('div').parentElement
    await userEvent.click(within(skillRow).getByRole('button', { name: 'Edit' }))

    // The proficiency <select> inside the now-open edit panel
    const selects = screen.getAllByRole('combobox')
    const editSelect = selects[selects.length - 1]
    await userEvent.selectOptions(editSelect, 'Expert')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(metabaseAPI.updateSkill).toHaveBeenCalledWith(
      'skill-1',
      expect.objectContaining({ name: 'Python', proficiency: 'Expert', years_experience: 2 }),
    ))
    // Reloads the list after a successful save
    await waitFor(() => expect(metabaseAPI.getSkills).toHaveBeenCalledTimes(2))
  })
})

describe('Metabase — Experience edit flow', () => {
  const EXPERIENCE = {
    id: 'exp-1',
    company: 'Acme',
    role: 'Engineer',
    location: null,
    start_date: 'Jan 2022',
    end_date: null,
    is_current: true,
    description: null,
    tech_stack: [],
  }

  it('ties the description field to the UI on edit (previously had no input at all)', async () => {
    metabaseAPI.getExperience.mockResolvedValue({ data: [EXPERIENCE] })
    metabaseAPI.updateExperience.mockResolvedValue({ data: { ...EXPERIENCE, description: 'Led platform work' } })

    render(<Metabase />)
    await userEvent.click(screen.getByRole('button', { name: 'Experience' }))
    await screen.findByText('Acme')

    await userEvent.click(screen.getByTitle('Edit experience'))
    // The "add experience" form above has an identical placeholder — the
    // edit-panel textarea is the one that mounts after clicking Edit.
    const textareas = screen.getAllByPlaceholderText('Describe your impact, responsibilities, and achievements')
    const descBox = textareas[textareas.length - 1]
    await userEvent.type(descBox, 'Led platform work')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(metabaseAPI.updateExperience).toHaveBeenCalledWith(
      'exp-1',
      expect.objectContaining({ description: 'Led platform work' }),
    ))
  })
})
