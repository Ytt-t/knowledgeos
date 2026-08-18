import { useEffect, useRef, useState } from 'react'
import { getMe, updateMe, updatePassword, uploadAvatar, uploadBanner } from '../api'

// V8: 设置页全部接真实数据（资料保存/头像/背景图/修改密码）
export default function Settings() {
  const [activeTab, setActiveTab] = useState('profile')
  const [me, setMe] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState('')

  // 表单
  const [nickname, setNickname] = useState('')
  const [email, setEmail] = useState('')
  const [bio, setBio] = useState('')
  const [signature, setSignature] = useState('')
  // 密码
  const [currentPwd, setCurrentPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [confirmPwd, setConfirmPwd] = useState('')

  const avatarRef = useRef(null)
  const bannerRef = useRef(null)

  const load = () => {
    getMe().then((u) => {
      setMe(u)
      setNickname(u.nickname)
      setEmail(u.email || '')
      setBio(u.bio || '')
      setSignature(u.signature || '')
    }).catch(() => {}).finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  const showToast = (msg) => {
    setToast(msg)
    setTimeout(() => setToast(''), 2500)
  }

  const handleSaveProfile = async () => {
    setSaving(true)
    try {
      const u = await updateMe({ nickname, email, bio, signature })
      setMe(u)
      showToast('✓ 资料已保存')
    } catch (e) {
      showToast('保存失败：' + (e?.response?.data?.detail || '请重试'))
    } finally {
      setSaving(false)
    }
  }

  const handleSavePassword = async () => {
    if (newPwd.length < 4) { showToast('密码至少 4 位'); return }
    if (newPwd !== confirmPwd) { showToast('两次输入的密码不一致'); return }
    setSaving(true)
    try {
      const r = await updatePassword({ current_password: currentPwd || null, new_password: newPwd })
      setMe({ ...me, has_password: r.has_password })
      setCurrentPwd(''); setNewPwd(''); setConfirmPwd('')
      showToast('✓ 密码已更新')
    } catch (e) {
      showToast(e?.response?.data?.detail || '修改失败')
    } finally {
      setSaving(false)
    }
  }

  const handleAvatar = async (f) => {
    if (!f) return
    try {
      const r = await uploadAvatar(f)
      setMe({ ...me, avatar_url: r.avatar_url })
      showToast('✓ 头像已更新')
    } catch (e) {
      showToast(e?.response?.data?.detail || '上传失败')
    }
  }

  const handleBanner = async (f) => {
    if (!f) return
    try {
      const r = await uploadBanner(f)
      setMe({ ...me, banner_url: r.banner_url })
      showToast('✓ 背景图已更新')
    } catch (e) {
      showToast(e?.response?.data?.detail || '上传失败')
    }
  }

  const tabs = [
    { key: 'profile', label: '个人信息' },
    { key: 'security', label: '账号安全' },
    { key: 'about', label: '关于' },
  ]

  if (loading) return <div className="text-neutral-400">加载中…</div>

  return (
    <div className="max-w-3xl relative">
      <h1 className="text-xl font-semibold text-neutral-900 mb-6">设置</h1>

      {toast && (
        <div className="fixed top-16 right-8 bg-neutral-900 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg z-50">
          {toast}
        </div>
      )}

      <div className="flex gap-8">
        {/* 左侧 Tab */}
        <aside className="w-40 shrink-0">
          <div className="space-y-0.5">
            {tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setActiveTab(t.key)}
                className={`w-full text-left px-3 py-2 rounded-md text-sm transition ${
                  activeTab === t.key
                    ? 'bg-neutral-100 text-neutral-900 font-medium'
                    : 'text-neutral-500 hover:text-neutral-900 hover:bg-neutral-50'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </aside>

        {/* 右侧内容 */}
        <section className="flex-1">
          {activeTab === 'profile' && (
            <div className="space-y-6">
              {/* 背景图 + 头像 */}
              <div className="relative h-32 rounded-xl overflow-hidden bg-neutral-50 border border-neutral-100">
                {me?.banner_url && (
                  <img src={me.banner_url} alt="" className="w-full h-full object-cover" />
                )}
                <button
                  onClick={() => bannerRef.current?.click()}
                  className="absolute bottom-2 right-2 px-2.5 py-1 bg-white/80 backdrop-blur text-xs text-neutral-600 rounded-lg hover:bg-white transition"
                >
                  更换背景图
                </button>
              </div>
              <div className="flex items-center gap-4 -mt-2 px-1">
                <div className="w-16 h-16 rounded-full bg-neutral-100 border-2 border-white overflow-hidden shadow flex items-center justify-center text-2xl text-neutral-400 cursor-pointer relative group"
                  onClick={() => avatarRef.current?.click()}>
                  {me?.avatar_url ? (
                    <img src={me.avatar_url} alt="" className="w-full h-full object-cover" />
                  ) : (
                    <span>{(me?.nickname || '学')[0]}</span>
                  )}
                  <span className="absolute inset-0 bg-black/30 text-white text-[10px] flex items-center justify-center opacity-0 group-hover:opacity-100 transition">
                    更换
                  </span>
                </div>
                <div>
                  <div className="text-sm font-medium text-neutral-900">{me?.nickname}</div>
                  <div className="text-xs text-neutral-400 mt-0.5">
                    知识 {me?.total_cards || 0} 张 · 复习 {me?.review_count || 0} 次
                  </div>
                </div>
              </div>

              {/* 表单 */}
              <div className="space-y-4 pt-2">
                <Field label="用户名" value={nickname} onChange={setNickname} />
                <Field label="邮箱" value={email} onChange={setEmail} />
                <Field label="个性签名" value={signature} onChange={setSignature} placeholder="一句话介绍自己…" />
                <Field label="个人简介" value={bio} onChange={setBio} textarea placeholder="多写一点关于自己…" />
              </div>

              <div>
                <button
                  onClick={handleSaveProfile}
                  disabled={saving}
                  className="px-6 py-2 bg-neutral-900 text-white rounded-lg text-sm font-medium hover:bg-neutral-800 disabled:opacity-40 transition-colors"
                >
                  {saving ? '保存中…' : '保存修改'}
                </button>
              </div>
            </div>
          )}

          {activeTab === 'security' && (
            <div className="space-y-5 max-w-sm">
              <p className="text-xs text-neutral-400 leading-relaxed">
                {me?.has_password
                  ? '修改密码：需要验证当前密码。'
                  : '还没有设置密码 —— 首次设置后，将来修改需验证。'}
              </p>
              {me?.has_password && (
                <div>
                  <label className="text-xs font-medium text-neutral-600 mb-1.5 block">当前密码</label>
                  <input
                    type="password"
                    value={currentPwd}
                    onChange={(e) => setCurrentPwd(e.target.value)}
                    className="w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm outline-none focus:border-neutral-400"
                  />
                </div>
              )}
              <div>
                <label className="text-xs font-medium text-neutral-600 mb-1.5 block">新密码</label>
                <input
                  type="password"
                  value={newPwd}
                  onChange={(e) => setNewPwd(e.target.value)}
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm outline-none focus:border-neutral-400"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-neutral-600 mb-1.5 block">确认新密码</label>
                <input
                  type="password"
                  value={confirmPwd}
                  onChange={(e) => setConfirmPwd(e.target.value)}
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm outline-none focus:border-neutral-400"
                />
              </div>
              <button
                onClick={handleSavePassword}
                disabled={saving}
                className="px-6 py-2 bg-neutral-900 text-white rounded-lg text-sm font-medium hover:bg-neutral-800 disabled:opacity-40 transition-colors"
              >
                {me?.has_password ? '更新密码' : '设置密码'}
              </button>
            </div>
          )}

          {activeTab === 'about' && (
            <div className="space-y-4">
              <div>
                <div className="text-xs text-neutral-400 mb-1">产品名称</div>
                <div className="text-sm text-neutral-900">KnowledgeOS</div>
              </div>
              <div>
                <div className="text-xs text-neutral-400 mb-1">版本</div>
                <div className="text-sm text-neutral-900">V8 — Personal Knowledge OS</div>
              </div>
              <div>
                <div className="text-xs text-neutral-400 mb-1">技术栈</div>
                <div className="text-sm text-neutral-900">React + FastAPI + SQLite + DeepSeek R1/V3</div>
              </div>
            </div>
          )}
        </section>
      </div>

      {/* 隐藏文件输入 */}
      <input ref={avatarRef} type="file" accept=".png,.jpg,.jpeg,.webp" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleAvatar(f); e.target.value = '' }} />
      <input ref={bannerRef} type="file" accept=".png,.jpg,.jpeg,.webp" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleBanner(f); e.target.value = '' }} />
    </div>
  )
}

function Field({ label, value, onChange, placeholder, textarea }) {
  return (
    <div>
      <label className="text-xs font-medium text-neutral-600 mb-1.5 block">{label}</label>
      {textarea ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={3}
          className="w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm outline-none focus:border-neutral-400 resize-none"
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm outline-none focus:border-neutral-400"
        />
      )}
    </div>
  )
}
