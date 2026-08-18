import { useEffect, useState } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import ProfileCard from './components/ProfileCard'
import { getMe } from './api'
import Home from './pages/Home'
import KnowledgeSpace from './pages/KnowledgeSpace'
import AIAssistant from './pages/AIAssistant'
import Review from './pages/Review'
import Settings from './pages/Settings'
import CardPage from './pages/CardPage'
import WrongBook from './pages/WrongBook'

const navItems = [
  { to: '/', label: '首页', icon: '◎', end: true },
  { to: '/space', label: '知识管理', icon: '❖' },
  { to: '/assistant', label: 'AI 助手', icon: '✦' },
  { to: '/review', label: '学习复习', icon: '◉' },
]

const bottomNav = [
  { to: '/settings', label: '设置', icon: '⚙' },
]

export default function App() {
  const location = useLocation()
  // V6: 侧边栏折叠（localStorage 记忆）
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem('kos_sidebar') === '1'
  )

  const toggleCollapsed = () => {
    const next = !collapsed
    setCollapsed(next)
    localStorage.setItem('kos_sidebar', next ? '1' : '0')
  }

  // V8: 右上角用户信息
  const [user, setUser] = useState(null)
  const [showProfile, setShowProfile] = useState(false)

  const loadUser = () => {
    getMe().then(setUser).catch(() => {})
  }

  useEffect(() => {
    loadUser()
  }, [])

  const pageTitles = {
    '/': '',
    '/space': '知识管理 / Knowledge Library',
    '/assistant': 'AI 助手 / AI Assistant',
    '/review': '学习复习 / Review',
    '/settings': '设置 / Settings',
    '/card': '知识详情 / Knowledge Card',
    '/wrong': 'AI 错题本 / Wrong Book',
  }
  // V6.1: 前缀匹配支持 /card/:cardId 等动态路由
  const pageTitle = Object.entries(pageTitles).find(
    ([key]) => location.pathname === key || (key !== '/' && location.pathname.startsWith(key + '/'))
  )?.[1] || ''

  return (
    <div className="flex min-h-screen bg-white">
      {/* 左侧边栏（V6: 可折叠） */}
      <aside
        className={`${
          collapsed ? 'w-14' : 'w-[200px]'
        } shrink-0 border-r border-neutral-100 flex flex-col fixed h-screen bg-white transition-all duration-200 z-20`}
      >
        {/* Logo / 折叠按钮 */}
        <div className={`border-b border-neutral-100 flex items-center ${collapsed ? 'justify-center py-5' : 'justify-between px-5 py-5'}`}>
          {!collapsed && (
            <div className="font-bold text-base text-neutral-900 tracking-tight">
              KnowledgeOS
            </div>
          )}
          <button
            onClick={toggleCollapsed}
            title={collapsed ? '展开侧边栏' : '折叠侧边栏'}
            className="text-neutral-400 hover:text-neutral-900 transition-colors text-sm"
          >
            {collapsed ? '⇥' : '⇤'}
          </button>
        </div>

        {/* 主导航 */}
        <nav className="flex-1 py-3 px-3 space-y-0.5">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              title={collapsed ? item.label : undefined}
              className={({ isActive }) =>
                `relative flex items-center ${collapsed ? 'justify-center px-0' : 'gap-2.5 px-3'} py-2 rounded-md text-sm transition ${
                  isActive
                    ? 'bg-neutral-100 text-neutral-900 font-medium'
                    : 'text-neutral-500 hover:text-neutral-900 hover:bg-neutral-50'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 bg-neutral-900 rounded-r" />
                  )}
                  <span className="text-sm w-4 text-center">{item.icon}</span>
                  {!collapsed && <span>{item.label}</span>}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* 底部导航 */}
        <div className="px-3 pb-4 space-y-0.5 border-t border-neutral-100 pt-3">
          {bottomNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              title={collapsed ? item.label : undefined}
              className={({ isActive }) =>
                `relative flex items-center ${collapsed ? 'justify-center px-0' : 'gap-2.5 px-3'} py-2 rounded-md text-sm transition ${
                  isActive
                    ? 'bg-neutral-100 text-neutral-900 font-medium'
                    : 'text-neutral-500 hover:text-neutral-900 hover:bg-neutral-50'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 bg-neutral-900 rounded-r" />
                  )}
                  <span className="text-sm w-4 text-center">{item.icon}</span>
                  {!collapsed && <span>{item.label}</span>}
                </>
              )}
            </NavLink>
          ))}
          <div
            title="KnowledgeOS"
            className={`w-full flex items-center ${collapsed ? 'justify-center px-0' : 'gap-2.5 px-3'} py-2 text-xs text-neutral-300`}
          >
            <span className="text-sm w-4 text-center">✦</span>
            {!collapsed && <span>KnowledgeOS · v0.9</span>}
          </div>
        </div>
      </aside>

      {/* 主内容区 */}
      <div className={`flex-1 transition-all duration-200 ${collapsed ? 'ml-14' : 'ml-[200px]'}`}>
        {/* 顶部栏（V8: 常显，右侧用户头像+昵称） */}
        <header className="h-14 border-b border-neutral-100 flex items-center justify-between px-8 sticky top-0 bg-white/80 backdrop-blur z-10">
          <h1 className="text-sm font-medium text-neutral-900">{pageTitle || ''}</h1>
          <button
            onClick={() => setShowProfile(true)}
            className="flex items-center gap-2.5 pl-2 pr-3 py-1.5 rounded-full hover:bg-neutral-50 transition"
          >
            <span className="w-7 h-7 rounded-full bg-neutral-100 border border-neutral-200 overflow-hidden flex items-center justify-center text-xs text-neutral-500">
              {user?.avatar_url ? (
                <img src={user.avatar_url} alt="" className="w-full h-full object-cover" />
              ) : (
                (user?.nickname || '学')[0]
              )}
            </span>
            <span className="text-xs text-neutral-700">{user?.nickname || '默认用户'}</span>
          </button>
        </header>

        {/* 内容 */}
        <main className="p-8">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/space" element={<KnowledgeSpace />} />
            <Route path="/assistant" element={<AIAssistant />} />
            <Route path="/review" element={<Review />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/card/:cardId" element={<CardPage />} />
            <Route path="/wrong" element={<WrongBook />} />
            {/* V9: AI 播客已下线（后端接口与数据保留，恢复只需加回路由与导入） */}
          </Routes>
        </main>
      </div>

      {/* V8: 个人信息卡（点头像弹出） */}
      {showProfile && (
        <ProfileCard
          onClose={() => {
            setShowProfile(false)
            loadUser()  // 资料可能已修改，刷新 header 头像
          }}
        />
      )}
    </div>
  )
}
