// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

import "./interfaces/IERC4626.sol";
import "./interfaces/IPriceOracle.sol";
import "./interfaces/IGlueXRouter.sol";
import "./HyperYieldVault.sol";

/**
 * @title VaultManagerMultiAsset
 * @notice Multi-asset strategy manager for HyperYieldVault using GlueX lending vaults.
 * @dev Assumes HyperYieldVault.asset is the baseAsset numeraire (e.g. USDC).
 *      Backend bot provides all routing logic via GlueX Router calldata.
 */
contract VaultManagerMultiAsset is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    /* ========== STATE ========== */

    HyperYieldVault public immutable hyperYieldVault;
    IERC20 public immutable baseAsset;
    IPriceOracle public priceOracle;

    struct Strategy {
        address vault;       // GlueX vault address (ERC4626)
        address underlying;  // underlying token used by this vault
        bool active;
    }

    // strategies keyed by vault address
    mapping(address => Strategy) public strategies;
    address[] public strategyList;

    // how many shares we hold in each vault
    mapping(address => uint256) public strategyShares;

    bool public isRebalancing;
    uint256 public constant REBALANCE_COOLDOWN = 5 seconds;
    uint256 public lastRebalanceTime;

    mapping(address => bool) public authorizedBots;

    event StrategyAdded(address indexed vault, address indexed underlying);
    event StrategyUpdated(address indexed vault, bool active);
    event StrategyRemoved(address indexed vault);
    event BotAuthorized(address indexed bot);
    event BotRevoked(address indexed bot);
    event PriceOracleUpdated(address indexed oracle);
    event PortfolioRebalanced(uint256 timestamp);
    event EmergencyWithdraw(address indexed vault, uint256 shares, uint256 assets);
    event IdleFundsPulled(uint256 amount);

    modifier onlyAuthorizedBot() {
        require(authorizedBots[msg.sender], "Not authorized");
        _;
    }

    modifier rebalanceCooldown() {
        require(block.timestamp >= lastRebalanceTime + REBALANCE_COOLDOWN, "Cooldown");
        _;
    }

    constructor(
        address _hyperYieldVault,
        address _baseAsset,
        address _priceOracle
    ) {
        require(_hyperYieldVault != address(0), "Invalid vault");
        require(_baseAsset != address(0), "Invalid asset");
        require(_priceOracle != address(0), "Invalid oracle");

        hyperYieldVault = HyperYieldVault(_hyperYieldVault);
        baseAsset = IERC20(_baseAsset);
        priceOracle = IPriceOracle(_priceOracle);
    }

    /* ========== ADMIN CONFIG ========== */

    function setPriceOracle(address _oracle) external onlyOwner {
        require(_oracle != address(0), "Invalid oracle");
        priceOracle = IPriceOracle(_oracle);
        emit PriceOracleUpdated(_oracle);
    }

    function authorizeBot(address bot) external onlyOwner {
        require(bot != address(0), "Invalid bot");
        authorizedBots[bot] = true;
        emit BotAuthorized(bot);
    }

    function revokeBot(address bot) external onlyOwner {
        authorizedBots[bot] = false;
        emit BotRevoked(bot);
    }

    function addStrategy(address vault, address underlying) external onlyOwner {
        require(vault != address(0), "Invalid vault");
        require(underlying != address(0), "Invalid underlying");
        require(!strategies[vault].active && strategies[vault].vault == address(0), "Exists");

        strategies[vault] = Strategy({
            vault: vault,
            underlying: underlying,
            active: true
        });
        strategyList.push(vault);

        emit StrategyAdded(vault, underlying);
    }

    function setStrategyActive(address vault, bool active) external onlyOwner {
        require(strategies[vault].vault != address(0), "Unknown strategy");
        strategies[vault].active = active;
        emit StrategyUpdated(vault, active);
    }

    function removeStrategy(address vault) external onlyOwner {
        require(strategies[vault].vault != address(0), "Unknown strategy");
        require(strategyShares[vault] == 0, "Non-zero position");

        delete strategies[vault];

        for (uint256 i = 0; i < strategyList.length; i++) {
            if (strategyList[i] == vault) {
                strategyList[i] = strategyList[strategyList.length - 1];
                strategyList.pop();
                break;
            }
        }

        emit StrategyRemoved(vault);
    }

    /* ========== VIEW: AUM ========== */

    /// @notice Total value of all strategies in baseAsset terms.
    /// @dev Used by HyperYieldVault.totalAssets().
    function getTotalManagedBaseAssets() external view returns (uint256 totalBase) {
        uint256 len = strategyList.length;
        for (uint256 i = 0; i < len; i++) {
            address vault = strategyList[i];
            Strategy memory s = strategies[vault];
            if (!s.active) continue;

            uint256 shares = strategyShares[vault];
            if (shares == 0) continue;

            // Try to convert our share balance into underlying units
            try IERC4626(vault).convertToAssets(shares) returns (uint256 underlyingAmount) {
                if (underlyingAmount == 0) continue;

                if (s.underlying == address(baseAsset)) {
                    totalBase += underlyingAmount;
                } else {
                    // use oracle to value in baseAsset
                    uint256 baseValue = priceOracle.quote(
                        s.underlying,
                        address(baseAsset),
                        underlyingAmount
                    );
                    totalBase += baseValue;
                }
            } catch {
                // If converting fails, fall back to zero contribution.
                // You can make this stricter (revert) if you prefer.
            }
        }
    }

    function getStrategies() external view returns (address[] memory) {
        return strategyList;
    }

    function canRebalance() external view returns (bool) {
        return block.timestamp >= lastRebalanceTime + REBALANCE_COOLDOWN;
    }

    /// @notice Get detailed position info for a strategy
    function getStrategyPosition(address vault) external view returns (
        address underlying,
        uint256 shares,
        uint256 underlyingAmount,
        uint256 baseValue,
        bool active
    ) {
        Strategy memory s = strategies[vault];
        require(s.vault != address(0), "Unknown strategy");

        shares = strategyShares[vault];
        underlying = s.underlying;
        active = s.active;

        if (shares > 0) {
            try IERC4626(vault).convertToAssets(shares) returns (uint256 amt) {
                underlyingAmount = amt;
                if (s.underlying == address(baseAsset)) {
                    baseValue = amt;
                } else {
                    baseValue = priceOracle.quote(s.underlying, address(baseAsset), amt);
                }
            } catch {
                underlyingAmount = 0;
                baseValue = 0;
            }
        }
    }

    /* ========== REBALANCING ========== */

    struct TargetAllocation {
        address vault;            // GlueX vault (must be active)
        uint256 underlyingAmount; // amount of that vault's underlying to deposit
    }

    /**
     * @notice Execute a full portfolio rebalance.
     * @dev Flow:
     *  0) Pull idle baseAsset from HyperYieldVault (new deposits).
     *  1) Withdraw from all strategies (maxWithdraw).
     *  2) Approve router for all tokens we hold, then call router with `swapCalldata`.
     *     - Backend bot ensures that after this call, the manager holds
     *       at least `underlyingAmount` for each TargetAllocation.
     *     - If swapping native tokens, bot sends ETH via msg.value which is forwarded to router.
     *  3) Deposit into target strategies (ERC4626.deposit).
     *  4) Return leftover baseAsset back to HyperYieldVault.
     */
    function executeRebalance(
        TargetAllocation[] calldata targets,
        address router,
        bytes calldata swapCalldata
    )
        external
        payable
        onlyAuthorizedBot
        rebalanceCooldown
        nonReentrant
    {
        require(!isRebalancing, "Already rebalancing");
        require(targets.length > 0, "No targets");

        isRebalancing = true;

        // 0) Pull idle baseAsset from vault (new deposits that aren't deployed yet)
        _pullIdleFundsFromVault();

        // 1) Withdraw from all current strategies (maxWithdraw)
        _withdrawAllStrategies();

        // 2) Router call for multi-asset swaps (if provided)
        if (router != address(0) && swapCalldata.length > 0) {
            _approveRouterForAllTokens(router);
            // Forward any ETH sent with this call to the router (for native token swaps)
            (bool success, bytes memory data) = router.call{value: msg.value}(swapCalldata);
            require(success, string(abi.encodePacked("Router call failed: ", data)));
        } else {
            // If no router call needed but ETH was sent, revert
            require(msg.value == 0, "Unexpected ETH");
        }

        // 3) Deposit into target strategies
        _resetStrategyShares();
        _depositIntoTargets(targets);

        // 4) Return leftover baseAsset to HyperYieldVault
        uint256 leftover = baseAsset.balanceOf(address(this));
        if (leftover > 0) {
            baseAsset.safeTransfer(address(hyperYieldVault), leftover);
            hyperYieldVault.receiveFromRebalance();
        }

        lastRebalanceTime = block.timestamp;
        isRebalancing = false;

        emit PortfolioRebalanced(block.timestamp);
    }

    /* ========== EMERGENCY FUNCTIONS ========== */

    /// @notice Emergency withdraw from a specific strategy
    function emergencyWithdraw(address vault) external onlyOwner {
        require(strategies[vault].vault != address(0), "Unknown strategy");
        
        uint256 shares = strategyShares[vault];
        require(shares > 0, "No position");

        try IERC4626(vault).redeem(shares, address(this), address(this)) returns (uint256 assets) {
            strategyShares[vault] = 0;
            emit EmergencyWithdraw(vault, shares, assets);
        } catch {
            // Try withdraw instead
            try IERC4626(vault).maxWithdraw(address(this)) returns (uint256 maxAssets) {
                if (maxAssets > 0) {
                    uint256 assets = IERC4626(vault).withdraw(maxAssets, address(this), address(this));
                    strategyShares[vault] = 0;
                    emit EmergencyWithdraw(vault, shares, assets);
                }
            } catch {
                revert("Emergency withdraw failed");
            }
        }
    }

    /// @notice Emergency return all baseAsset to vault
    function emergencyReturnFunds() external onlyOwner {
        uint256 balance = baseAsset.balanceOf(address(this));
        require(balance > 0, "No balance");
        
        baseAsset.safeTransfer(address(hyperYieldVault), balance);
        hyperYieldVault.receiveFromRebalance();
    }

    /* ========== INTERNAL HELPERS ========== */

    function _pullIdleFundsFromVault() internal {
        // Get idle baseAsset sitting in the vault (new deposits not yet deployed)
        uint256 vaultBalance = baseAsset.balanceOf(address(hyperYieldVault));
        
        if (vaultBalance > 0) {
            // Pull it into the manager for rebalancing
            hyperYieldVault.transferForRebalance(vaultBalance);
            emit IdleFundsPulled(vaultBalance);
        }
    }

    function _withdrawAllStrategies() internal {
        uint256 len = strategyList.length;
        for (uint256 i = 0; i < len; i++) {
            address vault = strategyList[i];
            Strategy memory s = strategies[vault];
            if (!s.active) continue;

            uint256 shares = strategyShares[vault];
            if (shares == 0) continue;

            // Try to withdraw all shares in underlying units
            try IERC4626(vault).redeem(shares, address(this), address(this)) returns (uint256) {
                // success, underlying tokens now in manager
            } catch {
                // Fallback: try maxWithdraw
                try IERC4626(vault).maxWithdraw(address(this)) returns (uint256 maxAssets) {
                    if (maxAssets > 0) {
                        IERC4626(vault).withdraw(maxAssets, address(this), address(this));
                    }
                } catch {
                    // If this fails, the strategy is effectively stuck; you may decide to revert here.
                    revert("Strategy withdraw failed");
                }
            }
        }
    }

    function _resetStrategyShares() internal {
        uint256 len = strategyList.length;
        for (uint256 i = 0; i < len; i++) {
            strategyShares[strategyList[i]] = 0;
        }
    }

    function _approveRouterForAllTokens(address router) internal {
        // Approve router to spend baseAsset & all strategy underlyings.
        // For simplicity we approve up to current balances each time.
        uint256 bal = baseAsset.balanceOf(address(this));
        if (bal > 0) {
            _safeApproveMax(address(baseAsset), router, bal);
        }

        uint256 len = strategyList.length;
        for (uint256 i = 0; i < len; i++) {
            Strategy memory s = strategies[strategyList[i]];
            if (!s.active) continue;

            IERC20 token = IERC20(s.underlying);
            uint256 amt = token.balanceOf(address(this));
            if (amt > 0) {
                _safeApproveMax(s.underlying, router, amt);
            }
        }
    }

    function _safeApproveMax(address token, address spender, uint256 amount) internal {
        IERC20 t = IERC20(token);
        uint256 current = t.allowance(address(this), spender);
        if (current < amount) {
            if (current > 0) {
                t.approve(spender, 0);
            }
            t.approve(spender, amount);
        }
    }

    function _depositIntoTargets(TargetAllocation[] calldata targets) internal {
        uint256 len = targets.length;
        for (uint256 i = 0; i < len; i++) {
            TargetAllocation calldata t = targets[i];
            Strategy memory s = strategies[t.vault];
            require(s.vault != address(0) && s.active, "Unknown strategy");

            IERC20 underlying = IERC20(s.underlying);
            require(t.underlyingAmount > 0, "Zero target");

            // Ensure we actually hold enough of this underlying
            uint256 bal = underlying.balanceOf(address(this));
            require(bal >= t.underlyingAmount, "Insufficient underlying");

            // Deposit into ERC4626 vault
            underlying.safeApprove(t.vault, 0);
            underlying.safeApprove(t.vault, t.underlyingAmount);

            uint256 sharesReceived = IERC4626(t.vault).deposit(t.underlyingAmount, address(this));
            require(sharesReceived > 0, "Zero shares");

            strategyShares[t.vault] = strategyShares[t.vault] + sharesReceived;
        }
    }
}
