// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

import "./interfaces/IERC7540.sol";

interface IVaultManagerView {
    function getTotalManagedBaseAssets() external view returns (uint256);
    function isRebalancing() external view returns (bool);
}

/**
 * @title HyperYieldVault
 * @notice ERC-7540 async vault, base-asset front end for multi-strategy GlueX allocation.
 * @dev Users always deposit / redeem the same `asset` (e.g. USDC). Manager may hold other tokens.
 */
contract HyperYieldVault is ERC20, IERC7540, ReentrancyGuard, Pausable, Ownable {
    using SafeERC20 for IERC20;

    /* ========== STATE ========== */

    IERC20 public immutable asset;        // Base asset (e.g. USDC)
    address public vaultManager;          // Strategy manager contract

    uint256 public constant SHARE_LOCK_PERIOD = 1 days;

    uint256 public requestNonce;

    struct DepositRequestData {
        address controller;
        uint256 assets;
        uint256 timestamp;
        bool claimed;
    }

    struct RedeemRequestData {
        address controller;
        uint256 shares;
        uint256 timestamp;
        bool claimed;
    }

    mapping(uint256 => DepositRequestData) public depositRequests;
    mapping(uint256 => RedeemRequestData) public redeemRequests;
    mapping(address => uint256) public shareUnlockTime;

    mapping(address => uint256[]) public userDepositRequests;
    mapping(address => uint256[]) public userRedeemRequests;

    event DepositClaimed(
        address indexed controller,
        uint256 indexed requestId,
        uint256 assets,
        uint256 shares
    );

    event RedeemClaimed(
        address indexed controller,
        uint256 indexed requestId,
        uint256 shares,
        uint256 assets
    );

    event VaultManagerUpdated(address indexed oldManager, address indexed newManager);

    constructor(
        address _asset,
        string memory _name,
        string memory _symbol
    ) ERC20(_name, _symbol) Ownable() {
        require(_asset != address(0), "Invalid asset");
        asset = IERC20(_asset);
    }

    /* ========== MODIFIERS ========== */

    modifier onlyVaultManager() {
        require(msg.sender == vaultManager, "Only manager");
        _;
    }

    modifier whenNotRebalancing() {
        if (vaultManager != address(0)) {
            try IVaultManagerView(vaultManager).isRebalancing() returns (bool r) {
                require(!r, "Rebalancing in progress");
            } catch {
                // If manager misconfigured, don't block deposits/redeems
            }
        }
        _;
    }

    /* ========== ERC-4626-like VIEW ========== */

    /// @notice Total assets in baseAsset terms.
    function totalAssets() public view returns (uint256) {
        uint256 idle = asset.balanceOf(address(this));
        uint256 managed = 0;

        if (vaultManager != address(0)) {
            try IVaultManagerView(vaultManager).getTotalManagedBaseAssets() returns (uint256 m) {
                managed = m;
            } catch {
                // ignore if manager call fails
            }
        }

        return idle + managed;
    }

    function convertToShares(uint256 assets_) public view returns (uint256) {
        uint256 supply = totalSupply();
        uint256 total = totalAssets();
        return supply == 0 || total == 0 ? assets_ : (assets_ * supply) / total;
    }

    function convertToAssets(uint256 shares_) public view returns (uint256) {
        uint256 supply = totalSupply();
        uint256 total = totalAssets();
        return supply == 0 ? shares_ : (shares_ * total) / supply;
    }

    /* ========== ERC-7540: DEPOSIT FLOW ========== */

    function requestDeposit(
        uint256 assets_,
        address controller,
        address owner
    ) external whenNotPaused nonReentrant returns (uint256 requestId) {
        require(assets_ > 0, "Zero assets");
        require(controller != address(0), "Invalid controller");

        asset.safeTransferFrom(owner, address(this), assets_);

        requestId = ++requestNonce;
        depositRequests[requestId] = DepositRequestData({
            controller: controller,
            assets: assets_,
            timestamp: block.timestamp,
            claimed: false
        });

        userDepositRequests[controller].push(requestId);

        emit DepositRequest(controller, owner, requestId, msg.sender, assets_);
    }

    function pendingDepositRequest(
        uint256 requestId,
        address controller
    ) external view returns (bool isPending, uint256 assets_) {
        DepositRequestData memory r = depositRequests[requestId];
        if (r.controller == controller && !r.claimed) {
            return (true, r.assets);
        }
        return (false, 0);
    }

    function claimableDepositRequest(
        uint256 requestId,
        address controller
    ) external view returns (bool isClaimable, uint256 shares_) {
        DepositRequestData memory r = depositRequests[requestId];
        if (r.controller == controller && !r.claimed) {
            shares_ = convertToShares(r.assets);
            return (true, shares_);
        }
        return (false, 0);
    }

    function deposit(
        uint256 assets_,
        address receiver,
        address controller
    ) external nonReentrant whenNotRebalancing returns (uint256 shares_) {
        uint256[] memory reqs = userDepositRequests[controller];
        uint256 matchedId = 0;

        for (uint256 i = 0; i < reqs.length; i++) {
            DepositRequestData storage r = depositRequests[reqs[i]];
            if (!r.claimed && r.assets == assets_ && r.controller == controller) {
                matchedId = reqs[i];
                break;
            }
        }
        require(matchedId != 0, "No matching request");

        DepositRequestData storage req = depositRequests[matchedId];
        require(!req.claimed, "Already claimed");

        shares_ = convertToShares(assets_);
        require(shares_ > 0, "Zero shares");

        req.claimed = true;

        _mint(receiver, shares_);
        shareUnlockTime[receiver] = block.timestamp + SHARE_LOCK_PERIOD;

        emit DepositClaimed(controller, matchedId, assets_, shares_);
    }

    /* ========== ERC-7540: REDEEM FLOW ========== */

    function requestRedeem(
        uint256 shares_,
        address controller,
        address owner
    ) external whenNotPaused nonReentrant returns (uint256 requestId) {
        require(shares_ > 0, "Zero shares");
        require(shares_ <= balanceOf(owner), "Insufficient shares");
        require(block.timestamp >= shareUnlockTime[owner], "Shares locked");

        _burn(owner, shares_);

        requestId = ++requestNonce;
        redeemRequests[requestId] = RedeemRequestData({
            controller: controller,
            shares: shares_,
            timestamp: block.timestamp,
            claimed: false
        });

        userRedeemRequests[controller].push(requestId);

        emit RedeemRequest(controller, owner, requestId, msg.sender, shares_);
    }

    function pendingRedeemRequest(
        uint256 requestId,
        address controller
    ) external view returns (bool isPending, uint256 shares_) {
        RedeemRequestData memory r = redeemRequests[requestId];
        if (r.controller == controller && !r.claimed) {
            return (true, r.shares);
        }
        return (false, 0);
    }

    function claimableRedeemRequest(
        uint256 requestId,
        address controller
    ) external view returns (bool isClaimable, uint256 assets_) {
        RedeemRequestData memory r = redeemRequests[requestId];
        if (r.controller == controller && !r.claimed) {
            assets_ = convertToAssets(r.shares);
            return (true, assets_);
        }
        return (false, 0);
    }

    function redeem(
        uint256 shares_,
        address receiver,
        address controller
    ) external nonReentrant whenNotRebalancing returns (uint256 assets_) {
        uint256[] memory reqs = userRedeemRequests[controller];
        uint256 matchedId = 0;

        for (uint256 i = 0; i < reqs.length; i++) {
            RedeemRequestData storage r = redeemRequests[reqs[i]];
            if (!r.claimed && r.shares == shares_ && r.controller == controller) {
                matchedId = reqs[i];
                break;
            }
        }
        require(matchedId != 0, "No matching request");

        RedeemRequestData storage req = redeemRequests[matchedId];
        require(!req.claimed, "Already claimed");

        assets_ = convertToAssets(shares_);
        require(assets_ > 0, "Zero assets");
        require(assets_ <= asset.balanceOf(address(this)), "Insufficient liquidity");

        req.claimed = true;

        asset.safeTransfer(receiver, assets_);

        emit RedeemClaimed(controller, matchedId, shares_, assets_);
    }

    /* ========== MANAGER HOOKS ========== */

    function setVaultManager(address _manager) external onlyOwner {
        require(_manager != address(0), "Invalid manager");
        emit VaultManagerUpdated(vaultManager, _manager);
        vaultManager = _manager;
    }

    /// @notice Called by manager to pull baseAsset out of the vault for rebalancing.
    function transferForRebalance(uint256 amount)
        external
        onlyVaultManager
        whenNotPaused
        nonReentrant
        returns (bool)
    {
        require(amount > 0, "Zero amount");
        require(amount <= asset.balanceOf(address(this)), "Insufficient balance");

        asset.safeTransfer(vaultManager, amount);
        return true;
    }

    /// @notice Marker for manager returning funds (optional).
    function receiveFromRebalance() external onlyVaultManager returns (bool) {
        return true;
    }

    /* ========== ADMIN ========== */

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    /* ========== ERC20 OVERRIDES ========== */

    function transfer(address to, uint256 amount) public override returns (bool) {
        require(block.timestamp >= shareUnlockTime[msg.sender], "Shares locked");
        return super.transfer(to, amount);
    }

    function transferFrom(address from, address to, uint256 amount) public override returns (bool) {
        require(block.timestamp >= shareUnlockTime[from], "Shares locked");
        return super.transferFrom(from, to, amount);
    }

    /* ========== DISABLE SYNC ERC-4626 ========== */

    function mint(uint256, address) external pure returns (uint256) {
        revert("Use async deposit flow");
    }

    function withdraw(uint256, address, address) external pure returns (uint256) {
        revert("Use async redeem flow");
    }
}
