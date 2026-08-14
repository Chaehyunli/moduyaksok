import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DoodleInput from './DoodleInput.vue'

describe('DoodleInput password mask', () => {
  it('shows one visible asterisk per character while keeping the native password input', async () => {
    const wrapper = mount(DoodleInput, {
      props: { modelValue: '', type: 'password' },
    })

    const input = wrapper.get('input')
    await input.setValue('sk-secret')

    expect(input.attributes('type')).toBe('password')
    expect(input.element.value).toBe('sk-secret')
    expect(wrapper.get('[data-testid="password-mask"]').text()).toBe('*********')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['sk-secret'])
  })

  it('removes the extra mask when the value is revealed', async () => {
    const wrapper = mount(DoodleInput, {
      props: { modelValue: 'sk-secret', type: 'password' },
    })

    await wrapper.setProps({ type: 'text' })

    expect(wrapper.find('[data-testid="password-mask"]').exists()).toBe(false)
    expect(wrapper.get('input').attributes('type')).toBe('text')
    expect(wrapper.get('input').element.value).toBe('sk-secret')
  })
})
