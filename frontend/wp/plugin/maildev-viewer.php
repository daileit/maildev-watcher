<?php
/**
 * Plugin Name: MailDev Viewer
 * Description: Quản lý, hiển thị email. Thêm Filter Type, Items Per Page, Export CSV & Balanced UI Toolbar.
 * Version: 2.8
 * Author: Dai Le (daileit.com)
 */

if (!defined('ABSPATH')) exit;

class MailDev_Viewer_Plugin {

    public function __construct() {
        add_action('admin_menu', [$this, 'add_admin_menu']);
        add_action('rest_api_init', [$this, 'register_api_routes']);
        add_shortcode('maildev_workspace', [$this, 'render_shortcode']);
    }

    public function add_admin_menu() {
        add_menu_page('MailDev Viewer', 'MailDev', 'manage_options', 'maildev-viewer', [$this, 'render_admin_page'], 'dashicons-email-alt', 30);
    }

    public function render_admin_page() {
        echo '<div class="wrap">';
        $this->render_app_html(false);
        echo '</div>';
    }

    public function render_shortcode() {
        if (!is_user_logged_in()) {
            return '<div style="padding: 40px; text-align: center; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; font-family: sans-serif;">
                        <h3 style="color: #0f172a; margin-bottom: 10px; font-size: 20px;">Yêu cầu đăng nhập</h3>
                        <p style="color: #64748b; margin-bottom: 24px;">Bạn cần đăng nhập để truy cập MailDev Workspace.</p>
                        <a href="' . esc_url(wp_login_url(get_permalink())) . '" style="background: linear-gradient(135deg, #3b82f6, #6366f1); color: white; padding: 10px 24px; text-decoration: none; border-radius: 8px; font-weight: 600; box-shadow: 0 4px 6px -1px rgba(59, 130, 246, 0.3);">Đăng nhập ngay</a>
                    </div>';
        }

        if (!current_user_can('read')) {
            return '<div style="padding: 40px; text-align: center; background: #fef2f2; border: 1px solid #fecaca; border-radius: 12px; color: #dc2626; font-family: sans-serif;">
                        <h3 style="margin:0 0 8px 0;">Từ chối truy cập</h3>
                        <p style="margin:0;">Tài khoản của bạn không có quyền xem dữ liệu này.</p>
                    </div>';
        }

        ob_start();
        $this->render_app_html(true);
        return ob_get_clean();
    }

    private function render_app_html($is_frontend = false) {
        $wrapper_class = $is_frontend ? 'md-app-wrapper is-frontend' : 'md-app-wrapper is-admin';
        ?>
        <div class="<?php echo $wrapper_class; ?>" id="maildev-app">
            
            <?php if (!$is_frontend): ?>
            <div class="maildev-header-main">
                <h1 class="maildev-app-title">
                    <span class="dashicons dashicons-email-alt"></span> Mail Workspace
                </h1>
            </div>
            <?php endif; ?>

            <div class="md-tabs-container" v-cloak>
                <button :class="['md-tab-btn', { active: currentTab === 'workspace' }]" @click="currentTab = 'workspace'">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
                    Workspace
                </button>
                <button :class="['md-tab-btn', { active: currentTab === 'stats' }]" @click="loadStats">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>
                    Thống kê
                </button>
            </div>

            <div v-show="currentTab === 'workspace'" :class="['maildev-container', { 'mobile-show-detail': activeMailId }]" v-if="!loadingInit" v-cloak>
                
                <div class="maildev-list-pane">
                    
                    <div class="md-toolbar">
                        <!-- Hàng 1: Search - Refresh - Export -->
                        <div class="md-toolbar-row">
                            <div class="md-search-wrapper">
                                <svg class="md-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                                <input type="text" v-model="searchQuery" @keyup.enter="handleSearch" placeholder="Tìm ID, From, To..." class="md-input md-control-height">
                            </div>
                            <button class="md-btn md-btn-icon md-control-height" @click="fetchEmails" title="Tải lại">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
                            </button>
                            <button class="md-btn md-export-btn md-control-height" @click="exportCSV" :disabled="isExporting" title="Xuất CSV">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                                <span class="md-hide-mobile">{{ isExporting ? 'Đang xuất...' : 'Export' }}</span>
                            </button>
                        </div>
                        
                        <!-- Hàng 2: PerPage Dropdown - Type Dropdown - Counter -->
                        <div class="md-toolbar-row">
                            <select v-model="perPage" @change="handlePerPageChange" class="md-select md-control-height md-select-perpage">
                                <option :value="50">50 / trang</option>
                                <option :value="100">100 / trang</option>
                                <option :value="500">500 / trang</option>
                                <option :value="1000">1000 / trang</option>
                            </select>

                            <select v-model="selectedType" @change="handleSearch" class="md-select md-control-height md-select-type">
                                <option value="">Tất cả loại</option>
                                <option v-for="type in availableTypes" :key="type" :value="type">{{ type }}</option>
                            </select>
                            
                            <div class="md-query-counter md-control-height" title="Tổng số email">
                                {{ totalItems }}
                            </div>
                        </div>
                    </div>

                    <div class="md-bulk-bar" v-if="isAdmin && emails.length > 0">
                        <label class="md-checkbox-label">
                            <input type="checkbox" v-model="selectAll">
                            <span>Chọn tất cả trang này</span>
                        </label>
                        <button class="md-btn md-btn-danger md-btn-small" :disabled="selectedMails.length === 0" @click="bulkDelete">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                            Xóa ({{ selectedMails.length }})
                        </button>
                    </div>
                    
                    <div class="md-list-body custom-scrollbar">
                        <div v-for="mail in emails" :key="mail.mailid" 
                             :class="['md-mail-item', { 'is-active': activeMailId === mail.mailid }]"
                             @click="viewDetail(mail.mailid)">
                            
                            <div class="md-mail-checkbox" v-if="isAdmin">
                                <input type="checkbox" :value="mail.mailid" v-model="selectedMails" @click.stop>
                            </div>
                            
                            <div class="md-mail-content">
                                <div class="md-mail-main">
                                    <div class="md-mail-line">
                                        <span class="md-label">To</span> 
                                        <strong class="md-mail-line-val">{{ mail.to }}</strong>
                                    </div>
                                    <div class="md-mail-line">
                                        <span class="md-label">From</span> 
                                        <span class="md-mail-line-val">{{ mail.from }}</span>
                                    </div>
                                    <div class="md-mail-line" style="margin-bottom:0;">
                                        <span class="md-label">Title</span> 
                                        <span class="md-mail-line-val">{{ mail.subject || '(Không có chủ đề)' }}</span>
                                    </div>
                                </div>
                                <div class="md-mail-meta-right">
                                    <div class="md-mail-time">{{ formatDateTime(mail.timestamp) }}</div>
                                    <span class="md-type-badge" v-if="mail.extracted_type">{{ mail.extracted_type }}</span>
                                    <div class="md-mail-id" :title="mail.mailid">{{ mail.mailid }}</div>
                                </div>
                            </div>
                        </div>
                        <div v-if="emails.length === 0" class="md-empty-state"><p>Không tìm thấy email nào.</p></div>
                    </div>

                    <div class="md-pagination" v-if="totalItems > 0">
                        <div class="md-page-nav-group">
                            <button class="md-btn md-btn-outline md-btn-small md-btn-icon-only" :disabled="currentPage === 1" @click="changePage(1)">&laquo;</button>
                            <button class="md-btn md-btn-outline md-btn-small md-btn-icon-only" :disabled="currentPage === 1" @click="changePage(currentPage - 1)">&lsaquo;</button>
                        </div>
                        <div class="md-page-info">
                            <input type="number" v-model.lazy="inputPage" @change="goToPage" @keyup.enter="goToPage" class="md-page-input" min="1" :max="totalPages || 1">
                            <span class="md-page-divider">/</span>
                            <span class="md-page-total">{{ totalPages || 1 }}</span>
                        </div>
                        <div class="md-page-nav-group">
                            <button class="md-btn md-btn-outline md-btn-small md-btn-icon-only" :disabled="currentPage >= totalPages" @click="changePage(currentPage + 1)">&rsaquo;</button>
                            <button class="md-btn md-btn-outline md-btn-small md-btn-icon-only" :disabled="currentPage >= totalPages" @click="changePage(totalPages)">&raquo;</button>
                        </div>
                    </div>
                </div>

                <div class="maildev-detail-pane">
                    <div v-if="activeMail" class="md-detail-wrapper custom-scrollbar">
                        
                        <div class="md-detail-header">
                            <div style="display: flex; flex-direction: column; gap: 10px; width: 100%;">
                                <button class="md-btn md-btn-outline md-btn-small md-mobile-back-btn" @click="closeDetailMobile">
                                    &larr; Quay lại danh sách
                                </button>
                                
                                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; width: 100%;">
                                    <h2 class="md-detail-subject">{{ activeMail.metadata.subject || '(Không có chủ đề)' }}</h2>
                                    <button v-if="isAdmin" class="md-btn md-btn-danger md-btn-outline md-btn-small md-hide-mobile" @click="deleteMail(activeMail.metadata.mailid)">Xóa</button>
                                </div>
                            </div>
                        </div>
                        
                        <div class="md-detail-meta">
                            <div class="md-avatar">{{ activeMail.metadata.from.charAt(0).toUpperCase() }}</div>
                            <div class="md-meta-info">
                                <div class="md-meta-from"><strong>{{ activeMail.metadata.from }}</strong></div>
                                <div class="md-meta-to">Đến: {{ activeMail.metadata.to }}</div>
                            </div>
                            <div class="md-meta-meta-right" style="text-align: right;">
                                <div class="md-meta-time">{{ formatDateTime(activeMail.metadata.timestamp) }}</div>
                                <span class="md-type-badge" v-if="activeMail.metadata.extracted_type" style="margin-top:4px; display:inline-block;">{{ activeMail.metadata.extracted_type }}</span>
                            </div>
                        </div>
                        
                        <div class="md-card md-summary-card" v-if="activeMail.metadata.extracted_code">
                            <div class="md-card-header">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>
                                AI Summary
                            </div>
                            <div class="md-summary-font">{{ activeMail.metadata.extracted_code }}</div>
                        </div>

                        <div class="md-card md-iframe-card">
                            <div class="md-card-header">Nội dung Email</div>
                            <div class="md-iframe-container" v-if="iframeContent">
                                <iframe :srcdoc="iframeContent" sandbox="allow-same-origin allow-popups"></iframe>
                            </div>
                            <div v-else class="md-empty-state">Không có dữ liệu HTML.</div>
                        </div>

                        <button v-if="isAdmin" class="md-btn md-btn-danger md-show-mobile" style="margin-top: 20px; width: 100%;" @click="deleteMail(activeMail.metadata.mailid)">Xóa Email Này</button>
                    </div>
                    
                    <div v-else class="md-empty-state md-no-selection">
                        <div class="md-empty-icon-wrap">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
                        </div>
                        <h3>Chưa chọn email</h3>
                        <p>Hãy click vào một email bên danh sách để xem chi tiết.</p>
                    </div>
                </div>
            </div>

            <div v-show="currentTab === 'stats'" class="maildev-container" style="background: #f8fafc; overflow-y: auto;" v-cloak>
                <div v-if="statsData" class="md-stats-wrapper">
                    <div class="md-stats-overview">
                        <div class="md-stat-card">
                            <div class="md-stat-title">Tổng số Email</div>
                            <div class="md-stat-value">{{ statsData.total }}</div>
                        </div>
                    </div>
                    
                    <div class="md-stats-grid">
                        <div class="md-stat-box">
                            <div class="md-stat-box-header">Phân bổ theo Loại (Type)</div>
                            <div class="md-stat-list">
                                <div class="md-stat-list-item" v-for="(item, idx) in statsData.top_types" :key="'type-'+idx">
                                    <div class="md-stat-email" style="text-transform: uppercase; font-weight: 700; color: #4f46e5;">{{ item.type || 'Không xác định' }}</div>
                                    <div class="md-stat-count">{{ item.count }} <span style="font-size:10px; color:#94a3b8">email</span></div>
                                </div>
                                <div v-if="!statsData.top_types.length" class="md-empty-state" style="padding: 20px;">Chưa có dữ liệu</div>
                            </div>
                        </div>

                        <div class="md-stat-box">
                            <div class="md-stat-box-header">Top 5 Người gửi nhiều nhất</div>
                            <div class="md-stat-list">
                                <div class="md-stat-list-item" v-for="(item, idx) in statsData.top_senders" :key="'send-'+idx">
                                    <div class="md-stat-email">{{ item.from }}</div>
                                    <div class="md-stat-count">{{ item.count }} <span style="font-size:10px; color:#94a3b8">email</span></div>
                                </div>
                                <div v-if="!statsData.top_senders.length" class="md-empty-state" style="padding: 20px;">Chưa có dữ liệu</div>
                            </div>
                        </div>
                        
                        <div class="md-stat-box">
                            <div class="md-stat-box-header">Top 5 Người nhận nhiều nhất</div>
                            <div class="md-stat-list">
                                <div class="md-stat-list-item" v-for="(item, idx) in statsData.top_receivers" :key="'recv-'+idx">
                                    <div class="md-stat-email">{{ item.to }}</div>
                                    <div class="md-stat-count">{{ item.count }} <span style="font-size:10px; color:#94a3b8">email</span></div>
                                </div>
                                <div v-if="!statsData.top_receivers.length" class="md-empty-state" style="padding: 20px;">Chưa có dữ liệu</div>
                            </div>
                        </div>
                        
                        <div class="md-stat-box md-col-span-full">
                            <div class="md-stat-box-header">Lưu lượng 7 ngày gần nhất</div>
                            <div class="md-bar-chart">
                                <div class="md-bar-row" v-for="(item, idx) in statsData.last_7_days" :key="'chart-'+idx">
                                    <div class="md-bar-label">{{ formatDateShort(item.date) }}</div>
                                    <div class="md-bar-track">
                                        <div class="md-bar-fill" :style="{ width: ((item.count / maxDailyCount) * 100) + '%' }"></div>
                                    </div>
                                    <div class="md-bar-value">{{ item.count }}</div>
                                </div>
                                <div v-if="!statsData.last_7_days.length" class="md-empty-state" style="padding: 20px;">Chưa có dữ liệu</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div v-else class="md-loading-screen">
                    <svg class="md-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="28" height="28"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
                    <span>Đang tải Thống kê...</span>
                </div>
            </div>

            <div v-if="loadingInit" class="md-loading-screen">
                <svg class="md-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="28" height="28"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
                <span>Đang tải Workspace...</span>
            </div>
        </div>

        <style>
            .md-app-wrapper { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #334155; box-sizing: border-box; line-height: 1.5; font-size: 14px;}
            .md-app-wrapper * { box-sizing: inherit; }
            .md-app-wrapper.is-admin { margin: 20px 20px 0 0; }
            .md-app-wrapper.is-frontend { margin: 0; padding: 0; }
            [v-cloak] { display: none !important; }

            .maildev-header-main { margin-bottom: 20px; }
            .maildev-app-title { font-size: 24px; font-weight: 700; color: #0f172a; display: flex; align-items: center; gap: 10px; margin: 0; letter-spacing: -0.5px;}
            
            .md-tabs-container { display: flex; gap: 10px; margin-bottom: 15px; border-bottom: 2px solid #e2e8f0; overflow-x: auto; flex-wrap: nowrap; }
            .md-tabs-container::-webkit-scrollbar { display: none; }
            .md-tab-btn { background: transparent; border: none; padding: 10px 20px; font-size: 15px; font-weight: 600; color: #64748b; cursor: pointer; display: flex; align-items: center; gap: 8px; border-bottom: 2px solid transparent; margin-bottom: -2px; transition: all 0.2s; white-space: nowrap;}
            .md-tab-btn svg { width: 18px; height: 18px; }
            .md-tab-btn:hover { color: #0f172a; }
            .md-tab-btn.active { color: #3b82f6; border-bottom-color: #3b82f6; }

            .maildev-container { display: flex; height: 85vh; min-height: 650px; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03); position: relative;}
            .maildev-list-pane { width: 40%; min-width: 440px; max-width: 580px; border-right: 1px solid #e2e8f0; display: flex; flex-direction: column; background: #fff; z-index: 10; height: 100%;}
            .maildev-detail-pane { flex: 1; display: flex; flex-direction: column; background: #fff; min-width: 0; position: relative;}
            
            /* Clean & Balanced 2-Row Grid Toolbar */
            .md-toolbar { padding: 12px 14px; border-bottom: 1px solid #e2e8f0; display: flex; flex-direction: column; gap: 8px; background: #f8fafc;}
            .md-toolbar-row { display: flex; gap: 8px; align-items: center; width: 100%; }
            
            .md-control-height { height: 36px !important; box-sizing: border-box; }
            
            .md-search-wrapper { position: relative; flex: 1; min-width: 0; display: flex; align-items: center;}
            .md-search-icon { position: absolute; left: 10px; color: #94a3b8; width: 16px; height: 16px; z-index: 2;}
            
            .md-input { width: 100%; padding: 0 10px 0 32px !important; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 13px; background: #fff; color: #0f172a; margin: 0 !important; }
            .md-input:focus, .md-select:focus { border-color: #3b82f6; background: #fff; outline: none; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15) !important;}
            
            .md-select { padding: 0 24px 0 10px !important; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 13px; background: #fff; color: #0f172a; cursor: pointer; box-shadow: inset 0 1px 2px rgba(0,0,0,0.02);}
            .md-select-perpage { flex: 1; min-width: 110px; }
            .md-select-type { flex: 1.5; min-width: 130px; }
            
            .md-query-counter { font-size: 12px; color: #fff; font-weight: 700; background: #3b82f6; padding: 0 12px; border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; box-shadow: 0 2px 4px rgba(59, 130, 246, 0.25); white-space: nowrap; flex-shrink: 0;}
            
            .md-btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 0 12px; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; border: 1px solid transparent; background: #3b82f6; color: #fff; transition: all 0.15s; white-space: nowrap;}
            .md-btn:hover { background: #2563eb; color: #fff; }
            .md-btn-icon { padding: 0 10px; background: #fff; color: #64748b; border: 1px solid #cbd5e1; flex-shrink: 0;}
            .md-btn-outline { background: #fff; border: 1px solid #cbd5e1; color: #475569; }
            
            .md-export-btn { background: #10b981; color: white; border: none; flex-shrink: 0;}
            .md-export-btn:hover { background: #059669; }
            
            .md-btn-danger { background: #ef4444; color: white; }
            .md-btn-danger:hover:not(:disabled) { background: #dc2626; }
            .md-btn-danger:disabled { background: #f1f5f9; color: #94a3b8; border: 1px solid #e2e8f0; cursor: not-allowed; box-shadow: none; opacity: 1;}
            .md-btn-danger.md-btn-outline { background: #fff; color: #ef4444; border-color: #fca5a5; }
            .md-btn-danger.md-btn-outline:hover { background: #fef2f2; border-color: #ef4444;}
            .md-btn-small { height: 32px !important; padding: 0 12px;}
            .md-btn-icon-only { padding: 0 8px;}

            .md-bulk-bar { padding: 10px 16px; background: #f1f5f9; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center;}
            .md-checkbox-label { display: flex; align-items: center; gap: 8px; cursor: pointer; font-weight: 600; font-size: 13px; color: #475569;}
            .md-checkbox-label input[type="checkbox"], .md-mail-checkbox input[type="checkbox"] { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #cbd5e1; cursor: pointer; accent-color: #3b82f6; margin:0;}
            
            .md-list-body { flex: 1; overflow-y: auto; background: #fff; min-height: 0;}
            .md-mail-item { display: flex; gap: 12px; padding: 14px 16px; border-bottom: 1px solid #e2e8f0; cursor: pointer; transition: all 0.15s ease; background: #fff;}
            .md-mail-item:hover { background: #f8fafc; }
            .md-mail-item.is-active { background: #eff6ff; border-left: 3px solid #3b82f6; padding-left: 13px;}
            .md-mail-checkbox { padding-top: 2px; }
            .md-mail-content { flex: 1; min-width: 0; display: flex; justify-content: space-between; gap: 12px; }
            
            .md-mail-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
            .md-mail-line { display: flex; align-items: center; font-size: 13px; color: #475569;}
            .md-label { 
                display: inline-block; 
                min-width: 44px;
                padding-right: 8px;
                font-size: 10px; 
                text-transform: uppercase; 
                font-weight: 700; 
                color: #94a3b8; 
                letter-spacing: 0.5px; 
                text-align: left;
            }
            .md-mail-line-val { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .md-mail-line strong { color: #0f172a; font-weight: 600; }

            .md-type-badge { display: inline-block; background: #f1f5f9; color: #475569; font-size: 10px; font-weight: 700; text-transform: uppercase; padding: 2px 6px; border-radius: 4px; border: 1px solid #e2e8f0;}
            .md-mail-meta-right { display: flex; flex-direction: column; align-items: flex-end; justify-content: space-between; flex-shrink: 0; gap: 6px;}
            .md-mail-time { font-size: 12px; color: #64748b; font-weight: 500;}
            .md-mail-id { font-family: ui-monospace, monospace; font-size: 11px; font-weight: 600; color: #4f46e5; background: #e0e7ff; padding: 2px 6px; border-radius: 4px; border: 1px solid #c7d2fe; max-width: 90px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

            .md-pagination { padding: 10px 16px; background: #fff; border-top: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center;}
            .md-page-nav-group { display: flex; gap: 4px; }
            .md-page-info { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: #475569;}
            .md-page-input { width: 44px; height: 32px; text-align: center; padding: 0 4px !important; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 13px; font-weight: 600;}

            .md-detail-wrapper { flex: 1; overflow-y: auto; padding: 30px; display: flex; flex-direction: column; }
            .md-detail-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; border-bottom: 1px solid #e2e8f0; padding-bottom: 15px;}
            .md-detail-subject { font-size: 22px; font-weight: 700; color: #0f172a; margin: 0; line-height: 1.3; word-break: break-word;}
            
            .md-detail-meta { display: flex; align-items: center; gap: 16px; padding: 16px; background: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 24px;}
            .md-avatar { width: 42px; height: 42px; border-radius: 8px; background: linear-gradient(135deg, #3b82f6, #6366f1); color: white; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 700; flex-shrink: 0;}
            .md-meta-info { flex: 1; min-width:0; display: flex; flex-direction: column; gap: 2px;}
            .md-meta-from, .md-meta-to { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 14px;}
            .md-meta-time { font-size: 13px; color: #64748b; font-weight: 500; display: flex; align-items: center;}

            .md-card { border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 20px; overflow: hidden; display: flex; flex-direction: column;}
            .md-card-header { background: #f8fafc; padding: 12px 16px; font-weight: 700; font-size: 12px; color: #475569; border-bottom: 1px solid #e2e8f0; text-transform: uppercase; display: flex; align-items: center; gap: 8px;}
            .md-summary-card { border-left: 4px solid #10b981; flex-shrink: 0; }
            .md-summary-font { font-family: Arial, sans-serif; font-size: 14px; color: #064e3b; background: #ecfdf5; padding: 16px; white-space: pre-wrap; word-break: break-word; margin:0;}
            
            .md-iframe-card { flex: 1; min-height: 500px; margin-bottom: 0;}
            .md-iframe-container { flex: 1; display: flex; background: #fff; min-height: 0;}
            .md-iframe-container iframe { width: 100%; height: 100%; border: none; flex: 1;}

            .md-empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 20px; color: #94a3b8; text-align: center; height: 100%;}
            .md-loading-screen { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; min-height: 400px; font-size: 15px; font-weight: 600; color: #64748b; gap: 16px;}
            .md-spin { animation: md-spin 1s linear infinite; color: #3b82f6;}
            @keyframes md-spin { 100% { transform: rotate(360deg); } }
            
            .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
            .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
            .custom-scrollbar::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 8px; }

            .md-stats-wrapper { padding: 24px; width: 100%; max-width: 1200px; margin: 0 auto;}
            .md-stats-overview { display: flex; gap: 20px; margin-bottom: 24px; }
            .md-stat-card { background: #fff; border-radius: 12px; padding: 20px; border: 1px solid #e2e8f0; flex: 1; box-shadow: 0 1px 3px rgba(0,0,0,0.05); text-align: center; border-bottom: 4px solid #3b82f6;}
            .md-stat-title { font-size: 13px; color: #64748b; font-weight: 700; text-transform: uppercase; margin-bottom: 8px;}
            .md-stat-value { font-size: 36px; font-weight: 800; color: #0f172a; line-height: 1;}
            
            .md-stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
            .md-col-span-full { grid-column: 1 / -1; }
            .md-stat-box { background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); overflow: hidden;}
            .md-stat-box-header { background: #f8fafc; padding: 14px 16px; font-weight: 700; color: #0f172a; border-bottom: 1px solid #e2e8f0; font-size: 13px;}
            
            .md-stat-list { display: flex; flex-direction: column; }
            .md-stat-list-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid #f1f5f9; }
            .md-stat-list-item:last-child { border-bottom: none; }
            .md-stat-email { font-weight: 600; color: #334155; word-break: break-all; padding-right: 15px; font-size: 13px;}
            .md-stat-count { background: #eff6ff; color: #3b82f6; padding: 2px 10px; border-radius: 12px; font-weight: 700; font-size: 12px; white-space: nowrap;}
            
            .md-bar-chart { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
            .md-bar-row { display: flex; align-items: center; gap: 12px; }
            .md-bar-label { width: 50px; font-size: 12px; color: #64748b; font-weight: 600; text-align: right;}
            .md-bar-track { flex: 1; background: #f1f5f9; height: 12px; border-radius: 6px; overflow: hidden; position: relative;}
            .md-bar-fill { background: linear-gradient(90deg, #60a5fa, #3b82f6); height: 100%; border-radius: 6px; transition: width 0.5s ease-out;}
            .md-bar-value { width: 35px; font-size: 12px; font-weight: 700; color: #0f172a;}

            /* =================== MOBILE ADJUSTMENTS =================== */
            .md-mobile-back-btn { display: none !important; }
            
            @media (max-width: 800px) {
                .maildev-container { flex-direction: column; height: 85vh; min-height: 600px; border-radius: 12px; position: relative;}
                .maildev-list-pane { width: 100%; min-width: 100%; max-width: 100%; border-right: none; flex: 1; min-height: 0; }
                .maildev-detail-pane { width: 100%; min-width: 100%; max-width: 100%; position: absolute; top: 0; left: 0; right: 0; bottom: 0; z-index: 20; background: #fff; transform: translateX(100%); transition: transform 0.3s ease-in-out; }
                .maildev-container.mobile-show-detail .maildev-detail-pane { transform: translateX(0); }
                .maildev-container.mobile-show-detail .maildev-list-pane { display: none; }
                
                .md-export-btn { padding: 0 8px; }
                .md-export-btn span.md-hide-mobile { display: none; }
                
                .md-mobile-back-btn { display: inline-flex !important; margin-bottom: 10px;}
                .md-hide-mobile { display: none !important; }
                .md-show-mobile { display: inline-flex !important; }
                
                .md-detail-wrapper { padding: 20px; }
                .md-detail-header { flex-direction: column; padding-bottom: 15px; margin-bottom: 15px;}
                .md-detail-subject { font-size: 20px; }
                .md-detail-meta { flex-direction: column; align-items: flex-start; gap: 10px; }
                .md-avatar { width: 36px; height: 36px; font-size: 16px; }
                .md-pagination { padding: 10px; gap: 5px; justify-content: center; flex-wrap: wrap;}
            }
        </style>

        <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
        <script>
            const { createApp, ref, computed, onMounted } = Vue;

            createApp({
                setup() {
                    const isAdmin = <?php echo current_user_can('manage_options') ? 'true' : 'false'; ?>;
                    
                    const currentTab = ref('workspace'); 
                    const statsData = ref(null);

                    const emails = ref([]);
                    const activeMailId = ref(null);
                    const activeMail = ref(null);
                    const loadingInit = ref(true);
                    
                    const currentPage = ref(1);
                    const totalPages = ref(1);
                    const totalItems = ref(0); 
                    const inputPage = ref(1); 
                    const searchQuery = ref('');
                    const selectedType = ref('');
                    const availableTypes = ref([]);
                    const perPage = ref(50);

                    const selectedMails = ref([]);
                    const isExporting = ref(false);

                    const apiBaseUrl = '<?php echo esc_url_raw(rest_url('maildev/v1')); ?>';
                    const nonce = '<?php echo wp_create_nonce('wp_rest'); ?>';
                    const headers = { 'Content-Type': 'application/json', 'X-WP-Nonce': nonce };

                    const selectAll = computed({
                        get: () => emails.value.length > 0 && selectedMails.value.length === emails.value.length,
                        set: (val) => { selectedMails.value = val ? emails.value.map(m => m.mailid) : []; }
                    });

                    const maxDailyCount = computed(() => {
                        if (!statsData.value || !statsData.value.last_7_days.length) return 1;
                        return Math.max(...statsData.value.last_7_days.map(d => d.count));
                    });

                    const iframeContent = computed(() => {
                        if (!activeMail.value || !activeMail.value.raw_content || !activeMail.value.raw_content.raw_body) return '';
                        let body = activeMail.value.raw_content.raw_body;
                        const fontStyle = '<style>body { font-family: Arial, Helvetica, sans-serif !important; line-height: 1.6; color: #333; padding: 15px;}</style>';
                        if (body.includes('</head>')) return body.replace('</head>', fontStyle + '</head>');
                        return fontStyle + body;
                    });

                    const formatDateTime = (datetimeStr) => {
                        const date = new Date(datetimeStr);
                        if(isNaN(date.getTime())) return datetimeStr;
                        const d = date.getDate().toString().padStart(2, '0');
                        const m = (date.getMonth() + 1).toString().padStart(2, '0');
                        const y = date.getFullYear();
                        const H = date.getHours().toString().padStart(2, '0');
                        const M = date.getMinutes().toString().padStart(2, '0');
                        return `${d}/${m}/${y} ${H}:${M}`;
                    };

                    const formatDateShort = (dateStr) => {
                        const date = new Date(dateStr);
                        if(isNaN(date.getTime())) return dateStr;
                        return `${date.getDate().toString().padStart(2, '0')}/${(date.getMonth() + 1).toString().padStart(2, '0')}`;
                    };

                    const fetchTypes = async () => {
                        try {
                            const res = await fetch(`${apiBaseUrl}/emails/types`, { headers });
                            availableTypes.value = await res.json();
                        } catch (err) { console.error('Lỗi fetch types:', err); }
                    };

                    const fetchEmails = async () => {
                        try {
                            const url = new URL(`${apiBaseUrl}/emails`);
                            url.searchParams.append('page', currentPage.value);
                            url.searchParams.append('per_page', perPage.value);
                            if (searchQuery.value) url.searchParams.append('search', searchQuery.value);
                            if (selectedType.value) url.searchParams.append('type', selectedType.value); 
                            
                            const res = await fetch(url, { headers });
                            const data = await res.json();
                            emails.value = data.items;
                            totalPages.value = data.totalPages;
                            totalItems.value = data.totalItems || 0; 
                            selectedMails.value = []; 
                            inputPage.value = currentPage.value; 
                        } catch (err) { console.error('Lỗi fetch:', err); }
                    };

                    const handlePerPageChange = () => {
                        currentPage.value = 1;
                        fetchEmails();
                    };

                    const exportCSV = async () => {
                        if (isExporting.value) return;
                        isExporting.value = true;
                        try {
                            const url = new URL(`${apiBaseUrl}/emails/export`);
                            if (searchQuery.value) url.searchParams.append('search', searchQuery.value);
                            if (selectedType.value) url.searchParams.append('type', selectedType.value);
                            
                            const res = await fetch(url, { headers });
                            if (!res.ok) throw new Error('Export failed');
                            const blob = await res.blob();
                            
                            const downloadUrl = window.URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = downloadUrl;
                            a.download = `maildev_export_${new Date().getTime()}.csv`;
                            document.body.appendChild(a);
                            a.click();
                            a.remove();
                            window.URL.revokeObjectURL(downloadUrl);
                        } catch (err) {
                            alert('Lỗi xuất file CSV');
                        } finally {
                            isExporting.value = false;
                        }
                    };

                    const loadStats = async () => {
                        currentTab.value = 'stats';
                        if (!statsData.value) {
                            try {
                                const res = await fetch(`${apiBaseUrl}/emails/stats`, { headers });
                                statsData.value = await res.json();
                            } catch (err) { console.error('Lỗi load thống kê'); }
                        }
                    };

                    const handleSearch = () => { currentPage.value = 1; fetchEmails(); };
                    const changePage = (page) => { 
                        const maxP = totalPages.value || 1;
                        if (page >= 1 && page <= maxP) { 
                            currentPage.value = page; 
                            fetchEmails(); 
                        } 
                    };
                    const goToPage = () => {
                        let p = parseInt(inputPage.value);
                        const maxP = totalPages.value || 1;
                        if(isNaN(p) || p < 1) p = 1;
                        if(p > maxP) p = maxP;
                        inputPage.value = p; 
                        changePage(p);
                    };

                    const viewDetail = async (mailid, updateUrl = true) => {
                        activeMailId.value = mailid;
                        activeMail.value = null; 
                        try {
                            const res = await fetch(`${apiBaseUrl}/emails/${mailid}`, { headers });
                            activeMail.value = await res.json();
                            if (updateUrl && !isAdmin) { 
                                const newUrl = new URL(window.location);
                                newUrl.searchParams.set('mailid', mailid);
                                window.history.pushState({}, '', newUrl);
                            }
                        } catch (err) { alert('Lỗi tải chi tiết'); }
                    };

                    const closeDetailMobile = () => {
                        activeMailId.value = null;
                        if (!isAdmin) {
                            const newUrl = new URL(window.location);
                            newUrl.searchParams.delete('mailid');
                            window.history.pushState({}, '', newUrl);
                        }
                    };

                    const deleteMail = async (mailid) => {
                        if (!isAdmin) return;
                        if (!confirm('Bạn có chắc chắn muốn xóa email này?')) return;
                        try {
                            const res = await fetch(`${apiBaseUrl}/emails/${mailid}`, { method: 'DELETE', headers });
                            if (res.ok) { 
                                activeMail.value = null; 
                                activeMailId.value = null; 
                                fetchEmails(); 
                                statsData.value = null; 
                            }
                        } catch (err) { alert('Lỗi xóa email'); }
                    };

                    const bulkDelete = async () => {
                        if (!isAdmin) return;
                        if (!confirm(`Xóa ${selectedMails.value.length} email đã chọn?`)) return;
                        try {
                            const res = await fetch(`${apiBaseUrl}/emails/bulk`, { method: 'POST', headers, body: JSON.stringify({ mailids: selectedMails.value }) });
                            if (res.ok) { 
                                activeMail.value = null; 
                                activeMailId.value = null; 
                                fetchEmails(); 
                                statsData.value = null; 
                            }
                        } catch (err) { alert('Lỗi xóa nhiều email'); }
                    };

                    onMounted(async () => {
                        await fetchTypes();
                        await fetchEmails();
                        const urlParams = new URLSearchParams(window.location.search);
                        const idFromUrl = urlParams.get('mailid');
                        if (idFromUrl) {
                            await viewDetail(idFromUrl, false);
                        }
                        loadingInit.value = false;
                    });

                    return { 
                        isAdmin, currentTab, statsData,
                        emails, activeMailId, activeMail, loadingInit, 
                        currentPage, totalPages, totalItems, inputPage, searchQuery, selectedType, availableTypes, perPage, selectedMails, selectAll, iframeContent, maxDailyCount, isExporting,
                        formatDateTime, formatDateShort, fetchEmails, handlePerPageChange, exportCSV, loadStats, handleSearch, changePage, goToPage, viewDetail, closeDetailMobile, deleteMail, bulkDelete
                    };
                }
            }).mount('#maildev-app');
        </script>
        <?php
    }

    public function register_api_routes() {
        $namespace = 'maildev/v1';
        
        register_rest_route($namespace, '/emails', ['methods' => 'GET', 'callback' => [$this, 'api_get_emails'], 'permission_callback' => [$this, 'check_read_permission']]);
        register_rest_route($namespace, '/emails/types', ['methods' => 'GET', 'callback' => [$this, 'api_get_types'], 'permission_callback' => [$this, 'check_read_permission']]);
        register_rest_route($namespace, '/emails/export', ['methods' => 'GET', 'callback' => [$this, 'api_export_csv'], 'permission_callback' => [$this, 'check_read_permission']]);
        register_rest_route($namespace, '/emails/stats', ['methods' => 'GET', 'callback' => [$this, 'api_get_stats'], 'permission_callback' => [$this, 'check_read_permission']]);
        register_rest_route($namespace, '/emails/(?P<mailid>[a-zA-Z0-9\-\_]+)', ['methods' => 'GET', 'callback' => [$this, 'api_get_detail'], 'permission_callback' => [$this, 'check_read_permission']]);
        
        register_rest_route($namespace, '/emails/(?P<mailid>[a-zA-Z0-9\-\_]+)', ['methods' => 'DELETE', 'callback' => [$this, 'api_delete_email'], 'permission_callback' => [$this, 'check_delete_permission']]);
        register_rest_route($namespace, '/emails/bulk', ['methods' => 'POST', 'callback' => [$this, 'api_bulk_delete'], 'permission_callback' => [$this, 'check_delete_permission']]);
    }

    public function check_read_permission() { return current_user_can('read'); }
    public function check_delete_permission() { return current_user_can('manage_options'); }

    public function api_get_types($request) {
        global $wpdb;
        $types = $wpdb->get_col("SELECT DISTINCT extracted_type FROM mw_metadata WHERE extracted_type IS NOT NULL AND extracted_type != ''");
        return rest_ensure_response($types ?: []);
    }

    public function api_get_emails($request) {
        global $wpdb;
        $requested_per_page = (int) $request->get_param('per_page');
        $per_page = ($requested_per_page > 0) ? min(1000, max(10, $requested_per_page)) : 50;

        $page = max(1, (int) $request->get_param('page'));
        $offset = ($page - 1) * $per_page;
        $search = sanitize_text_field($request->get_param('search'));
        $type = sanitize_text_field($request->get_param('type'));

        $where = "1=1";
        if (!empty($search)) {
            $like_search = '%' . $wpdb->esc_like($search) . '%';
            $where .= $wpdb->prepare(" AND (mailid LIKE %s OR `from` LIKE %s OR `to` LIKE %s)", $like_search, $like_search, $like_search);
        }
        if (!empty($type)) {
            $where .= $wpdb->prepare(" AND extracted_type = %s", $type);
        }

        $total_items = (int) $wpdb->get_var("SELECT COUNT(id) FROM mw_metadata WHERE $where");
        $total_pages = ceil($total_items / $per_page);
        $query = "SELECT id, mailid, `from`, `to`, subject, timestamp, extracted_type FROM mw_metadata WHERE $where ORDER BY id DESC LIMIT %d OFFSET %d";
        $results = $wpdb->get_results($wpdb->prepare($query, $per_page, $offset));

        return rest_ensure_response([
            'items' => $results, 
            'totalPages' => $total_pages, 
            'totalItems' => $total_items
        ]);
    }

    public function api_export_csv($request) {
        global $wpdb;
        $search = sanitize_text_field($request->get_param('search'));
        $type = sanitize_text_field($request->get_param('type'));
        
        $where = "1=1";
        if (!empty($search)) {
            $like_search = '%' . $wpdb->esc_like($search) . '%';
            $where .= $wpdb->prepare(" AND (mailid LIKE %s OR `from` LIKE %s OR `to` LIKE %s)", $like_search, $like_search, $like_search);
        }
        if (!empty($type)) {
            $where .= $wpdb->prepare(" AND extracted_type = %s", $type);
        }

        $results = $wpdb->get_results("SELECT mailid, `from`, `to`, subject, timestamp, extracted_type, extracted_code FROM mw_metadata WHERE $where ORDER BY id DESC", ARRAY_A);

        header('Content-Type: text/csv; charset=utf-8');
        header('Content-Disposition: attachment; filename=maildev_export_' . date('Ymd_His') . '.csv');
        
        $output = fopen('php://output', 'w');
        fputs($output, "\xEF\xBB\xBF");
        fputcsv($output, ['Mail ID', 'From', 'To', 'Subject', 'Time', 'Type', 'Summary Code']);
        
        if ($results) {
            foreach ($results as $row) {
                fputcsv($output, $row);
            }
        }
        fclose($output);
        exit;
    }

    public function api_get_stats($request) {
        global $wpdb;
        $total = $wpdb->get_var("SELECT COUNT(id) FROM mw_metadata");
        
        $last_7_days = $wpdb->get_results("SELECT DATE(timestamp) as date, COUNT(*) as count FROM mw_metadata GROUP BY DATE(timestamp) ORDER BY date DESC LIMIT 7");
        $last_7_days = array_reverse($last_7_days);
        
        $top_types = $wpdb->get_results("SELECT extracted_type as type, COUNT(*) as count FROM mw_metadata WHERE extracted_type IS NOT NULL AND extracted_type != '' GROUP BY extracted_type ORDER BY count DESC");
        $top_senders = $wpdb->get_results("SELECT `from`, COUNT(*) as count FROM mw_metadata GROUP BY `from` ORDER BY count DESC LIMIT 5");
        $top_receivers = $wpdb->get_results("SELECT `to`, COUNT(*) as count FROM mw_metadata GROUP BY `to` ORDER BY count DESC LIMIT 5");

        return rest_ensure_response([
            'total' => $total ?: 0,
            'last_7_days' => $last_7_days ?: [],
            'top_types' => $top_types ?: [],
            'top_senders' => $top_senders ?: [],
            'top_receivers' => $top_receivers ?: []
        ]);
    }

    public function api_get_detail($request) {
        global $wpdb;
        $mailid = sanitize_text_field($request['mailid']);
        $metadata = $wpdb->get_row($wpdb->prepare("SELECT * FROM mw_metadata WHERE mailid = %s", $mailid));
        $raw_content = $wpdb->get_row($wpdb->prepare("SELECT * FROM mw_raw_content WHERE mailid = %s", $mailid));
        if (!$metadata) return new WP_Error('not_found', 'Email not found', ['status' => 404]);
        return rest_ensure_response(['metadata' => $metadata, 'raw_content' => $raw_content]);
    }

    public function api_delete_email($request) {
        global $wpdb;
        $mailid = sanitize_text_field($request['mailid']);
        $wpdb->delete('mw_metadata', ['mailid' => $mailid], ['%s']);
        $wpdb->delete('mw_raw_content', ['mailid' => $mailid], ['%s']);
        return rest_ensure_response(['success' => true]);
    }

    public function api_bulk_delete($request) {
        global $wpdb;
        $mailids = $request->get_param('mailids');
        if (empty($mailids) || !is_array($mailids)) return new WP_Error('invalid', 'No ID', ['status' => 400]);
        $clean_ids = array_map('sanitize_text_field', $mailids);
        $placeholders = implode(',', array_fill(0, count($clean_ids), '%s'));
        $wpdb->query($wpdb->prepare("DELETE FROM mw_metadata WHERE mailid IN ($placeholders)", ...$clean_ids));
        $wpdb->query($wpdb->prepare("DELETE FROM mw_raw_content WHERE mailid IN ($placeholders)", ...$clean_ids));
        return rest_ensure_response(['success' => true]);
    }
}

new MailDev_Viewer_Plugin();